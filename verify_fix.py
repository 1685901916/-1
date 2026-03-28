"""验证所有 enhancer 的色彩正确性"""
import sys, numpy as np, cv2, pathlib, tempfile
sys.path.insert(0, 'src')

from mobi_manga_app.enhancers.base import EnhanceOptions

opts = EnhanceOptions(mode='standard', scale=1.5)
tmp = pathlib.Path(tempfile.gettempdir())

# ---- 制造测试图：模拟漫画灰度 jpg（含暗部阴影 = 值30、中灰 = 128、白 = 240）----
gray_src = np.array([
    [30,  30,  30,  128, 128, 128, 240, 240, 240],
    [30,  30,  30,  128, 128, 128, 240, 240, 240],
    [30,  30,  30,  128, 128, 128, 240, 240, 240],
], dtype=np.uint8)
# 保存为 jpg 再读回（模拟真实流程：IMREAD_UNCHANGED 读灰度 jpg → ndim=2）
cv2.imencode('.jpg', gray_src)[1].tofile(str(tmp / 'src_gray.jpg'))

from mobi_manga_app.enhancers.opencv_enhancer import OpenCVEnhancer
from mobi_manga_app.enhancers.lanczos_enhancer import LanczosEnhancer
from mobi_manga_app.enhancers.waifu2x_enhancer import Waifu2xEnhancer

results = {}
for cls in [OpenCVEnhancer, LanczosEnhancer, Waifu2xEnhancer]:
    name = cls().name
    out_path = tmp / f'out_{name}.jpg'
    try:
        e = cls()
        e.enhance_file(tmp / 'src_gray.jpg', out_path, opts)
        out = cv2.imdecode(np.fromfile(str(out_path), dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        h, w = out.shape[:2]
        exp_h = int(round(gray_src.shape[0] * opts.scale))
        exp_w = int(round(gray_src.shape[1] * opts.scale))
        # 取暗部区域均值（左上角）
        dark_region = out[:max(1, h//3), :max(1, w//3)]
        if dark_region.ndim == 3:
            dark_mean = float(dark_region.mean())
        else:
            dark_mean = float(dark_region.mean())
        size_ok = (h == exp_h and w == exp_w)
        # 暗部不应该变成纯黑（<5），期望保留一定亮度（>15）
        dark_ok = dark_mean > 15
        print(f"[{'✓' if size_ok and dark_ok else '✗'}] {name:20s} "
              f"shape={out.shape}  期望={exp_h}x{exp_w}  "
              f"暗部均值={dark_mean:.1f}({'保留' if dark_ok else '变黑!'})")
        results[name] = size_ok and dark_ok
    except Exception as ex:
        print(f"[✗] {name:20s} 异常: {ex}")
        results[name] = False

print()
all_ok = all(results.values())
print("=== 结论:", "全部通过 ✓" if all_ok else "存在问题 ✗")

