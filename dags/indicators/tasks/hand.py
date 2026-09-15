import rasterio
import numpy as np
import matplotlib.pyplot as plt

input_merit = 'MERIT_Hydro.tif'

with rasterio.open(input_merit) as src:
    profile = src.profile
    
    hand = src.read(7).astype(np.float32)  # hnd
    
    if src.nodata is not None:
        hand[hand == src.nodata] = np.nan
    
    profile.update(dtype=rasterio.float32, count=1, nodata=np.nan)
    with rasterio.open('MERIT_HAND.tif', 'w', **profile) as dst:
        dst.write(hand, 1)
    
    
    plt.figure(figsize=(10, 10))
    vmin_h, vmax_h = np.nanpercentile(hand, [2, 98])
    im = plt.imshow(np.clip(hand, 0, 50), cmap='Blues_r', vmin=0, vmax=50)
    plt.colorbar(im, label='Высота над ближайшим водотоком (м)')
    plt.title(f'HAND')
    plt.axis('off')
    plt.tight_layout()
    plt.show()
    