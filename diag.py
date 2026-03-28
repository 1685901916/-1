"""诊断脚本：查 RE 失败原因 + 阴影变黑根因"""
import sys, numpy as np, cv2, tempfile, pathlib
sys.path.insert(0, 'src')
from mobi_manga_app.enhancers.base import EnhanceOptions

# ===== 1. RE 模型真实报错 =====
print('=== 1. RealESRGAN 加载错误 ===')
try:
    from mobi_manga_app.enhancers import _fix_basicsr
    from realesrgan import RealESRGANer
    from realesrgan.archs.srvgg_arch import SRVGGNetCompact
    m = SRVGGNetCompact(num_in_ch=3, num_out_ch=3, num_feat=64, num_conv=16, upscale=4, act_type='prelu')
    RealESRGANer(scale=4,
        model_path='https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-animevideov3.pth',
        model=m, tile=0, tile_pad=10, pre_pad=0, half=False)
    print('  OK - 加载成功')
except Exception as e:
    import traceback
    print(f'  FAIL: {type(e).__name__}: {e}')
    traceback.print_exc()

# ===== 2. IMREAD_UNCHANGED 漫画jpg/png 会给几通道？ =====
print('\n=== 2. IMREAD_UNCHANGED 通道检查 ===')
tmp = pathlib.Path(tempfile.gettempdir())

# 模拟灰度漫画页
gray_img = np.full((20, 20), 100, dtype=np.uint8)
cv2.imencode('.jpg', gray_img)[1].tofile(str(tmp/'g.jpg'))
cv2.imencode('.png', gray_img)[1].tofile(str(tmp/'g.png'))
for fn in ['g.jpg', 'g.png']:
    arr = cv2.imdecode(np.fromfile(str(tmp/fn), dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    print(f'  {fn}: shape={arr.shape}  ndim={arr.ndim}  dtype={arr.dtype}')

# 模拟彩色漫画页（BGR）
color_img = np.zeros((20, 20, 3), dtype=np.uint8)
color_img[:, :, 0] = 30   # B
color_img[:, :, 1] = 80   # G
color_img[:, :, 2] = 200  # R
cv2.imencode('.jpg', color_img)[1].tofile(str(tmp/'c.jpg'))
arr = cv2.imdecode(np.fromfile(str(tmp/'c.jpg'), dtype=np.uint8), cv2.IMREAD_UNCHANGED)
print(f'  c.jpg: shape={arr.shape}  ndim={arr.ndim}  pixel[0,0]={arr[0,0]}  (BGR expected: ~[30,80,200])')

# ===== 3. opencv enhance_gray 输出 ndim? =====
print('\n=== 3. OpenCV 灰度输入输出 ndim ===')
from mobi_manga_app.enhancers.opencv_enhancer import OpenCVEnhancer
oc = OpenCVEnhancer()
opts = EnhanceOptions(mode='standard', scale=1.0)
gray2 = np.full((20, 20), 80, dtype=np.uint8)
out = oc.enhance(gray2, opts)
print(f'  输入 ndim=2 → 输出 shape={out.shape}  ndim={out.ndim}')
# imencode 对 ndim=2 正常吗？
ok, buf = cv2.imencode('.jpg', out)
print(f'  imencode OK={ok}  buf len={len(buf)}')

# ===== 4. waifu2x 灰度后 COLOR_BGR2GRAY 的值对比 =====
print('\n=== 4. Waifu2x 灰度还原准确性 ===')
# 阴影区域：原始值 30（深灰）
shadow = np.full((10, 10), 30, dtype=np.uint8)
pil_rgb = __import__('PIL.Image', fromlist=['Image']).Image.fromarray(shadow, mode='L').convert('RGB')
arr_rgb = np.array(pil_rgb)
print(f'  灰度30 → PIL RGB: {arr_rgb[0,0]}')  # 应该是 [30,30,30]
bgr = arr_rgb[:, :, ::-1].copy()
back_gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
print(f'  还原灰度: {back_gray[0,0]}  (期望≈30)')

print('\n=== 诊断完成 ===')

