import rasterio
import numpy as np
import matplotlib.pyplot as plt

input_path = 'S1_km.tif'
output_vv_db = 'S1_VV_dB.tif'
output_vh_db = 'S1_VH_dB.tif'
output_ratio_db = 'S1_VV_VH_dB.tif'

with rasterio.open(input_path) as src:
    profile = src.profile
    

    vv_linear = src.read(1).astype(np.float32)
    vh_linear = src.read(2).astype(np.float32)
        
    vv_linear = np.where(vv_linear <= 0, 1e-10, vv_linear)
    vh_linear = np.where(vh_linear <= 0, 1e-10, vh_linear)
    
    vv_db = 10.0 * np.log10(vv_linear)
    vh_db = 10.0 * np.log10(vh_linear)
    
    ratio_linear = vv_linear / vh_linear
    
    ratio_db = vv_db - vh_db
    
    def save_tif(data, output_path, profile, nodata=np.nan):
        profile.update(
            dtype=rasterio.float32,
            count=1,
            nodata=nodata
        )
        with rasterio.open(output_path, 'w', **profile) as dst:
            dst.write(data.astype(np.float32), 1)
        print(f"Сохранено: {output_path}")
    
    save_tif(vv_db, output_vv_db, profile)
    save_tif(vh_db, output_vh_db, profile)
    save_tif(ratio_db, output_ratio_db, profile)
    
    fig, axes = plt.subplots(1, 3, figsize=(16, 14))
    
    im1 = axes[0].imshow(np.clip(vv_db, -30, 0), cmap='gray', vmin=-30, vmax=0)
    axes[0].set_title('VV (dB) — клип [-30, 0]')
    plt.colorbar(im1, ax=axes[0], label='dB')
    
    im2 = axes[1].imshow(np.clip(vh_db, -30, 0), cmap='gray', vmin=-30, vmax=0)
    axes[1].set_title('VH (dB) — клип [-30, 0]')
    plt.colorbar(im2, ax=axes[1], label='dB')
    
    im3 = axes[2].imshow(np.clip(ratio_db, -5, 15), cmap='viridis', vmin=-5, vmax=15)
    axes[2].set_title('VV/VH ratio (dB) — клип [-5, 15]')
    plt.colorbar(im3, ax=axes[2], label='dB')
    
    for ax in axes.flatten():
        ax.axis('off')
    
    plt.tight_layout()
    plt.show()
    