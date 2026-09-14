import rasterio
import os
import matplotlib.pyplot as plt
import numpy as np

with rasterio.open('S2_km.tif') as src:
    
    profile = src.profile
    
    blue = src.read(1).astype(np.float32)# B2 - синий
    green = src.read(2).astype(np.float32)  # B3 - зеленый
    red = src.read(3).astype(np.float32)  # B4 - красный
    nir = src.read(4).astype(np.float32)  # B8 - ближний ИК
    swir1 = src.read(5).astype(np.float32)  # B11 - Swir 1
    swir2 = src.read(6).astype(np.float32)  # B12 - Swir 2
    scl = src.read(7).astype(np.float32) * 10000.0  # SCL - Маска
    
    aweish = (blue + 2.5 * green - 1.5 * (nir + swir1) - 0.25 * swir2)
    
    
    cloud_shadow_mask = np.isin(scl, [3, 8, 9, 10])
    aweish[cloud_shadow_mask] = np.nan
    
    # profile.update(dtype=rasterio.float32, count=1, nodata=np.nan)
    # with rasterio.open(os.path.join('.', 'S2_AWEIsh.tif'), 'w', **profile) as dst:
    #     dst.write(aweish.astype(np.float32), 1)
    
    plt.figure(figsize=(10, 8))
    valid_aweish = aweish[~np.isnan(aweish)]
    vmin, vmax = np.percentile(valid_aweish, [2, 98])
    
    im = plt.imshow(aweish, cmap='RdYlBu_r', vmin=vmin, vmax=vmax)
    plt.colorbar(im, label='AWEIsh')
    plt.title('AWEIsh')
    plt.axis('off')
    plt.tight_layout()
    plt.show()



# import rasterio
# import matplotlib.pyplot as plt
# import numpy as np

# input_path = 'S2_km.tif'
# output_path = 'S2_AWEIsh.tif'

# with rasterio.open(input_path) as src:
#     profile = src.profile
    
#     blue = src.read(1).astype(np.float32)    # B2
#     green = src.read(2).astype(np.float32)   # B3
#     red = src.read(3).astype(np.float32)     # B4 
#     nir = src.read(4).astype(np.float32)     # B8
#     swir1 = src.read(5).astype(np.float32)   # B11
#     swir2 = src.read(6).astype(np.float32)  # B12
#     scl = src.read(7).astype(np.uint8)      # SCL
    
#     aweish = (blue 
#               + 2.5 * green 
#               - 1.5 * (nir + swir1) 
#               - 0.25 * swir2)
    
#     # Применяем маску SCL (обнуляем облака и тени, чтобы они не влияли на статистику)
#     # Коды SCL: 3=тень, 8=облака, 9=высокие облака, 10=перистые облака
#     cloud_shadow_mask = np.isin(scl, [3, 8, 9, 10])
#     aweish[cloud_shadow_mask] = np.nan
    
#     # Сохранение результата
#     profile.update(
#         dtype=rasterio.float32,
#         count=1,
#         nodata=np.nan
#     )
    
#     with rasterio.open(output_path, 'w', **profile) as dst:
#         dst.write(aweish.astype(np.float32), 1)
    
#     print(f"Индекс AWEIsh успешно сохранен в {output_path}")
    
#     # Визуализация
#     plt.figure(figsize=(10, 8))
    
#     # Игнорируем NaN при расчете минимума и максимума для красивой цветовой шкалы
#     valid_aweish = aweish[~np.isnan(aweish)]
#     vmin, vmax = np.percentile(valid_aweish, [2, 98])
    
#     im = plt.imshow(aweish, cmap='RdYlBu_r', vmin=vmin, vmax=vmax)
#     plt.colorbar(im, label='AWEIsh ( > 0 = вода, < 0 = суша/тень)')
#     plt.title('AWEIsh (Automated Water Extraction Index - Shadow)')
#     plt.axis('off')
#     plt.tight_layout()
#     plt.savefig('S2_AWEIsh_preview.png', dpi=150, bbox_inches='tight')
#     plt.show()
    
#     # Быстрая статистика
#     water_pixels = (aweish > 0) & (~np.isnan(aweish))
#     print(f"\nСтатистика:")
#     print(f"Диапазон значений AWEIsh: от {np.nanmin(aweish):.4f} до {np.nanmax(aweish):.4f}")
#     print(f"Пикселей, классифицированных как вода (AWEIsh > 0): {np.sum(water_pixels)}")
#     # 1 пиксель Sentinel-2 = 10x10 м = 100 кв.м = 0.01 га
#     print(f"Примерная площадь воды по AWEIsh: {np.sum(water_pixels) * 0.01:.2f} га")