import base64
from loguru import logger
from langchain.tools import tool

from agentchat.core.models.manager import ModelManager
from agentchat.settings import app_settings

@tool(parse_docstring=True)
def image_to_text(image_path: str):
    """
    根据用户提供的图片路径描述图片内容。

    Args:
        image_path (str): 用户提供的图片路径。

    Returns:
        str: 描述图片内容的结果。
    """
    return _image_to_text(image_path)

def _image_to_text(image_path):
    qwen_vl_model = app_settings.multi_models.qwen_vl
    if not qwen_vl_model.api_key or not qwen_vl_model.model_name:
        logger.warning("多模态（视觉）模型未配置，跳过图片理解")
        return ("图片理解功能未配置，无法识别图片。"
                "该工具依赖多模态视觉模型（如通义千问 qwen-vl），DeepSeek 等纯文本模型无法替代。"
                "如需使用，请在 config.yaml 的 multi_models.qwen_vl 中填写你自己的 api_key、base_url 和 model_name（例如 qwen-vl-plus）。")

    def encode_image():
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    client = ModelManager.get_qwen_vl_model()

    image_type = image_path.split('.')[-1]
    base64_image = encode_image()

    response = client.invoke(
        [
            {
                "role": "system",
                "content": [{"type": "text", "text": "You are a helpful assistant."}]},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        # 需要注意，传入BASE64，图像格式（即image/{format}）需要与支持的图片列表中的Content Type保持一致。"f"是字符串格式化的方法。
                        # PNG图像：  f"data:image/png;base64,{base64_image}"
                        # JPEG图像： f"data:image/jpeg;base64,{base64_image}"
                        # WEBP图像： f"data:image/webp;base64,{base64_image}"
                        "image_url": {"url": f"data:image/{image_type};base64,{base64_image}"},
                    },
                    {"type": "text", "text": "图中描绘的是什么景象?"},
                ],
            }
        ],
    )
    return response.content
