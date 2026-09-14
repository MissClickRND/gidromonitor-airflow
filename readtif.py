import rasterio
import matplotlib.pyplot as plt
import numpy as np

with rasterio.open('S2_km.tif') as src:
    # Чтение полос (B2, B3, B4, B8)
    blue = src.read(1)    # B2 - синий
    green = src.read(2)   # B3 - зеленый
    red = src.read(3)     # B4 - красный
    nir = src.read(4)     # B8 - ближний ИК
    
    # Создание RGB композита
    rgb = np.stack([red, green, blue], axis=-1)
    rgb = np.clip(rgb * 3, 0, 1)
    
    plt.figure(figsize=(10, 10))
    plt.imshow(rgb)
    plt.title('Sentinel-2 Natural Color')
    plt.axis('off')
    plt.show()
    
    # Расчет NDVI (вегетационный индекс)
    ndvi = (nir - red) / (nir + red + 1e-10)
    
    plt.figure(figsize=(10, 10))
    plt.imshow(ndvi, cmap='RdYlGn')
    plt.colorbar(label='NDVI')
    plt.title('NDVI Vegetation Index')
    plt.axis('off')
    plt.show()
    
    # Расчет NDWI (Нормализованный разностный водный индекс)
    ndwi = (green - nir) / (green + nir + 1e-10)
    
    plt.figure(figsize=(10, 10))
    plt.imshow(ndwi, cmap='RdYlGn')
    plt.colorbar(label='NDWI')
    plt.title('NDWI Water Index')
    plt.axis('off')
    plt.show()
    
    

with rasterio.open('S1_km.tif') as src:
    vv = src.read(1)   # VV
    vh = src.read(2)   # VH 
    
    fig, axes = plt.subplots(1, 2, figsize=(15, 5))
    
    im1 = axes[0].imshow(10 * np.log10(np.abs(vv) + 1e-10), cmap='gray')
    axes[0].set_title('VV Polarization')
    plt.colorbar(im1, ax=axes[0])
    
    im2 = axes[1].imshow(10 * np.log10(np.abs(vh) + 1e-10), cmap='gray')
    axes[1].set_title('VH Polarization')
    plt.colorbar(im2, ax=axes[1])
    
    plt.tight_layout()
    plt.show()