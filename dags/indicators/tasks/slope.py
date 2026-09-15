import rasterio
import numpy as np
import matplotlib.pyplot as plt

input_dem = 'GLO30_km.tif'
PIXEL_SIZE = 10.0

with rasterio.open(input_dem) as src:
    
    dem = src.read(1).astype(np.float32)
    
    profile = src.profile
        
    if src.nodata is not None:
        dem[dem == src.nodata] = np.nan
    
    dy, dx = np.gradient(dem, PIXEL_SIZE, PIXEL_SIZE)
    
    slope_rad = np.arctan(np.sqrt(dx**2 + dy**2))
    
    slope_deg = np.degrees(slope_rad)

    slope_deg = np.where(np.isnan(dem), np.nan, slope_deg)
    
    
    profile.update(dtype=rasterio.float32, count=1, nodata=np.nan)
    with rasterio.open('DEM_Slope_degrees.tif', 'w', **profile) as dst:
        dst.write(slope_deg.astype(np.float32), 1)
                
                
    plt.figure(figsize=(10, 8))   
    
    im = plt.imshow(np.clip(slope_deg, 0, 30), cmap='YlOrRd', vmin=0, vmax=30)
    plt.title('Slope')
    plt.colorbar(im, label='градусы')
    plt.tight_layout()
    plt.show()