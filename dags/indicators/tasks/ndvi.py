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
    
    ndvi = (nir - red) / (nir + red + 1e-10)
    
    
    cloud_shadow_mask = np.isin(scl, [3, 8, 9, 10])
    ndvi[cloud_shadow_mask] = np.nan
        
    profile.update(dtype=rasterio.float32, count=1, nodata=np.nan)
    with rasterio.open(os.path.join('.', 'S2_NDVI.tif'), 'w', **profile) as dst:
        dst.write(ndvi.astype(np.float32), 1)
        
    plt.figure(figsize=(10, 8))
    valid_ndvi = ndvi[~np.isnan(ndvi)]
    vmin, vmax = np.percentile(valid_ndvi, [2, 98])
        
    im = plt.imshow(ndvi, cmap='RdYlGn', vmin=vmin, vmax=vmax)
    plt.colorbar(im, label='NDVI')
    plt.title('NDVI')
    plt.axis('off')
    plt.tight_layout()
    plt.show()
