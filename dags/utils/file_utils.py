"""
Универсальные утилиты для работы с файлами: определение типа,
распаковка архивов, сборка многослойных GeoTIFF.
Подходит для любых моделей и пайплайнов.
"""
import os
import re
import tempfile
import zipfile
import logging
from typing import Dict, List, Optional, Any

import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling

log = logging.getLogger(__name__)


ZIP_MAGICS = (b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08')
TIFF_MAGICS = (b'II*\x00', b'MM\x00*')


def detect_file_kind(path: str) -> str:

    if not os.path.exists(path):
        raise FileNotFoundError(f"Файл не найден: {path}")
    
    with open(path, 'rb') as f:
        head = f.read(16)
    
    if any(head.startswith(m) for m in ZIP_MAGICS):
        return 'zip'
    if any(head.startswith(m) for m in TIFF_MAGICS):
        return 'tiff'
    
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.tif', '.tiff'):
        return 'tiff'
    
    return 'unknown'


S2_BANDS_CONFIG = {
    'bands_order': ['B2', 'B3', 'B4', 'B8', 'B11', 'B12', 'SCL'],
    'patterns': {
        'B2':  r'(?i)(^|[^a-z0-9])b0*2([^a-z0-9]|$)',
        'B3':  r'(?i)(^|[^a-z0-9])b0*3([^a-z0-9]|$)',
        'B4':  r'(?i)(^|[^a-z0-9])b0*4([^a-z0-9]|$)',
        'B8':  r'(?i)(^|[^a-z0-9])b0*8([^a-z0-9]|$)',
        'B11': r'(?i)(^|[^a-z0-9])b11([^a-z0-9]|$)',
        'B12': r'(?i)(^|[^a-z0-9])b12([^a-z0-9]|$)',
        'SCL': r'(?i)(^|[^a-z0-9])scl([^a-z0-9]|$)',
    },
    'target_band': 'B2',
    'normalize_bands': ['B2', 'B3', 'B4', 'B8', 'B11', 'B12'],
    'mask_bands': ['SCL'],
}
S1_BANDS_CONFIG = {
    'bands_order': ['VV', 'VH'],
    'patterns': {
        'VV': r'(?i)(^|[^a-z0-9])vv([^a-z0-9]|$)',
        'VH': r'(?i)(^|[^a-z0-9])vh([^a-z0-9]|$)',
    },
    'target_band': 'VV',
    'normalize_bands': [],
    'mask_bands': [],
}



def _find_member(names: List[str], pattern: str) -> str:

    rx = re.compile(pattern)
    matches = [n for n in names if rx.search(os.path.basename(n))]
    
    if not matches:
        raise FileNotFoundError(f"Не найден файл по паттерну: {pattern}")
    
    matches.sort(key=lambda n: (
        not n.lower().endswith(('.tif', '.tiff', '.jp2')),
        len(n),
    ))
    return matches[0]

def build_multiband_tiff(
    zip_path: str,
    out_tiff_path: str,
    bands_config: Dict[str, Any],
) -> str:
    bands_order = bands_config['bands_order']
    patterns = bands_config['patterns']
    target_band = bands_config.get('target_band', bands_order[0])
    normalize_bands = set(bands_config.get('normalize_bands', []))
    mask_bands = set(bands_config.get('mask_bands', []))
    
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if not n.endswith('/')]
        
        log.info(f"Содержимое ZIP-архива ({len(names)} файлов):")
        for n in names[:20]:
            log.info(f"  {n}")
        if len(names) > 20:
            log.info(f"  ... и ещё {len(names) - 20} файлов")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            zf.extractall(tmpdir)
            
            arrays = {}
            profiles = {}
            
            for band in bands_order:
                if band not in patterns:
                    raise ValueError(f"Не задан паттерн для полосы {band}")
                
                member = _find_member(names, patterns[band])
                extracted_path = os.path.join(tmpdir, member.replace('/', os.sep))
                
                with rasterio.open(extracted_path) as src:
                    if src.count != 1:
                        log.warning(
                            f"Полоса {band}: ожидался однополосный файл, "
                            f"получено {src.count}. Берём первую полосу."
                        )
                    
                    arr = src.read(1).astype(np.float32)
                    arrays[band] = arr
                    profiles[band] = src.profile.copy()
                    
                    log.info(
                        f"{band}: {member}, "
                        f"shape={arr.shape}, "
                        f"dtype={src.dtypes[0]}"
                    )
            
            if target_band not in arrays:
                target_band = bands_order[0]
            
            target_profile = profiles[target_band].copy()
            target_shape = arrays[target_band].shape
            
            log.info(f"Целевая сетка: {target_band}, shape={target_shape}")
            
            for band in bands_order:
                if arrays[band].shape != target_shape:
                    resampling = (
                        Resampling.nearest 
                        if band in mask_bands 
                        else Resampling.bilinear
                    )
                    
                    dst_arr = np.full(target_shape, np.nan, dtype=np.float32)
                    
                    reproject(
                        source=arrays[band],
                        destination=dst_arr,
                        src_transform=profiles[band]['transform'],
                        src_crs=profiles[band]['crs'],
                        dst_transform=target_profile['transform'],
                        dst_crs=target_profile['crs'],
                        src_nodata=profiles[band].get('nodata'),
                        dst_nodata=np.nan,
                        resampling=resampling,
                    )
                    
                    arrays[band] = dst_arr
                    log.info(f"{band}: репроецирована к сетке {target_band}")
            
            for band in bands_order:
                if band in normalize_bands:
                    arr = arrays[band]
                    finite = arr[np.isfinite(arr)]
                    
                    if finite.size > 0 and np.nanmax(np.abs(finite)) > 10.0:
                        arrays[band] = arr / 10000.0
                        log.info(f"{band}: значения разделены на 10000 (DN -> reflectance)")
            

            stack = np.stack([arrays[b] for b in bands_order], axis=0)
            
            out_profile = target_profile.copy()
            out_profile.update(
                driver='GTiff',
                count=stack.shape[0],
                dtype=rasterio.float32,
                nodata=np.nan,
            )
            
            out_profile.pop('photometric', None)
            out_profile.pop('interleave', None)
            
            with rasterio.open(out_tiff_path, 'w', **out_profile) as dst:
                dst.write(stack.astype(np.float32))
                
                for i, band in enumerate(bands_order, start=1):
                    dst.set_band_description(i, band)
            
            log.info(f" Многослойный GeoTIFF сохранен: {out_tiff_path}")
            log.info(f"   Порядок полос: {bands_order}")
            return out_tiff_path


def process_downloaded_file(
    file_path: str,
    bands_config: Optional[Dict[str, Any]] = None,
    force_convert: bool = False,
) -> tuple[str, str]:

    kind = detect_file_kind(file_path)
    log.info(f"Определенный тип файла: {kind}")
    
    if kind == 'tiff':
        return file_path, 'tiff'
    
    elif kind == 'zip':
        if bands_config is None:
            raise ValueError(
                "Получен ZIP-архив, но не передан bands_config для сборки GeoTIFF. "
                "Передайте конфигурацию (например, S2_BANDS_CONFIG)."
            )
        
        stacked_path = file_path + '.stacked.tif'
        build_multiband_tiff(file_path, stacked_path, bands_config)
        return stacked_path, 'zip_converted'
    
    elif kind in ('png', 'jpeg', 'pdf'):
        log.warning(f"Получен файл неожиданного типа: {kind}. Возвращаем как есть.")
        return file_path, kind
    
    else:
        try:
            with rasterio.open(file_path) as src:
                if src.count > 0:
                    log.info("Файл успешно открыт rasterio, хотя тип не распознан.")
                    return file_path, 'tiff'
        except Exception:
            pass
        
        raise ValueError(
            f"Не удалось обработать файл: {file_path}. "
            f"Тип: {kind}. Проверьте содержимое файла."
        )