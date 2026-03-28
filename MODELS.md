# 画质提升模型说明

## 可用模型

### 1. OpenCV (默认，无需额外安装)
- **名称**: `opencv`
- **优点**: 无需额外依赖，任何电脑都能用
- **缺点**: 效果一般，文字可能模糊
- **适用**: 快速处理，无 GPU 环境

### 2. Real-ESRGAN Anime (推荐)
- **名称**: `realesrgan-anime`
- **优点**: 专门针对动漫/漫画优化，文字最清晰
- **缺点**: 需要额外安装依赖
- **适用**: 追求最佳画质

### 3. Real-ESRGAN
- **名称**: `realesrgan`
- **优点**: 通用 AI 超分辨率模型
- **缺点**: 需要额外安装依赖
- **适用**: 通用图像增强

### 4. Waifu2x
- **名称**: `waifu2x`
- **优点**: 经典动漫图像放大工具
- **缺点**: 需要额外安装依赖
- **适用**: 动漫风格图像

## 安装方法

### 基础安装（仅 OpenCV）
```bash
python -m pip install -e .
```

### 安装 Real-ESRGAN（推荐）
```bash
pip install realesrgan basicsr
```

### 安装 Waifu2x
```bash
pip install waifu2x-ncnn-vulkan-python
```

## 使用方法

### 查看可用模型
```bash
python -m mobi_manga_app.cli list-models
```

### 使用指定模型处理
```bash
# 使用 Real-ESRGAN Anime（推荐，画质最好）
python -m mobi_manga_app.cli process "漫画.cbz" --workspace .work/output --model realesrgan-anime

# 使用 Waifu2x
python -m mobi_manga_app.cli process "漫画.cbz" --workspace .work/output --model waifu2x

# 使用 Real-ESRGAN
python -m mobi_manga_app.cli process "漫画.cbz" --workspace .work/output --model realesrgan

# 使用 OpenCV（默认）
python -m mobi_manga_app.cli process "漫画.cbz" --workspace .work/output --model opencv

# 自动选择（优先 AI 模型）
python -m mobi_manga_app.cli process "漫画.cbz" --workspace .work/output
```

## 扩展性设计

项目采用插件式架构，添加新模型只需：

1. 在 `src/mobi_manga_app/enhancers/` 创建新的 enhancer 类
2. 继承 `BaseEnhancer` 并实现必要方法
3. 在 `registry.py` 中注册

示例见 `realesrgan_enhancer.py`
