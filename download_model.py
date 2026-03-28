"""下载 realesr-animevideov3.pth 模型文件，自动尝试镜像"""
import urllib.request
import pathlib
import sys
import time

FILENAME = "realesr-animevideov3.pth"
ORIG_URL = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/" + FILENAME

MIRRORS = [
    "https://ghfast.top/" + ORIG_URL,
    "https://mirror.ghproxy.com/" + ORIG_URL,
    "https://gh.ddlc.top/" + ORIG_URL,
    "https://ghproxy.net/" + ORIG_URL,
    ORIG_URL,  # 直连最后兜底
]

TARGET_DIR = pathlib.Path(__file__).parent / ".models"
TARGET_DIR.mkdir(exist_ok=True)
TARGET = TARGET_DIR / FILENAME

if TARGET.exists() and TARGET.stat().st_size > 1024 * 1024:
    print(f"已存在: {TARGET}  ({TARGET.stat().st_size/1024/1024:.1f} MB)")
    sys.exit(0)

HEADERS = {"User-Agent": "Mozilla/5.0"}

# 先探测哪个镜像可用
print("探测可用镜像...")
chosen_url = None
chosen_size = 0
for url in MIRRORS:
    try:
        req = urllib.request.Request(url, method="HEAD", headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as r:
            size = int(r.headers.get("Content-Length", 0))
            mb = size / 1024 / 1024
            print(f"  ✓ {url[:70]}  {mb:.1f} MB")
            if chosen_url is None:
                chosen_url = url
                chosen_size = size
    except Exception as e:
        print(f"  ✗ {url[:70]}  {type(e).__name__}")

if chosen_url is None:
    print("\n所有镜像均不可达，请手动下载：")
    print(f"  {ORIG_URL}")
    print(f"  放到: {TARGET}")
    sys.exit(1)

print(f"\n使用: {chosen_url[:70]}")
print(f"目标: {TARGET}")
print(f"大小: {chosen_size/1024/1024:.1f} MB")
print("开始下载...")

def reporthook(block, block_size, total):
    downloaded = block * block_size
    if total > 0:
        pct = min(100, downloaded * 100 // total)
        mb_done = downloaded / 1024 / 1024
        mb_total = total / 1024 / 1024
        print(f"\r  {pct}%  {mb_done:.1f}/{mb_total:.1f} MB", end="", flush=True)

try:
    req = urllib.request.Request(chosen_url, headers=HEADERS)
    tmp = TARGET.with_suffix(".tmp")
    urllib.request.urlretrieve(chosen_url, tmp, reporthook)
    print()
    tmp.rename(TARGET)
    final_mb = TARGET.stat().st_size / 1024 / 1024
    print(f"下载完成: {TARGET}  ({final_mb:.1f} MB)")
except Exception as e:
    print(f"\n下载失败: {e}")
    if tmp.exists():
        tmp.unlink()
    sys.exit(1)

