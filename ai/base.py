from openai import AsyncOpenAI
import aiohttp
import base64
import os

class AiManager:
    _MODEL = os.getenv("MODEL")
    _CLIENT = AsyncOpenAI(
            base_url=os.getenv("AI_BASE_URL"),
            api_key=os.getenv("API_KEY"),
            max_retries=3
        )

    @classmethod
    async def request_ai(cls, promt: str, post_text: str = None, image_paths: list[str] = None) -> str:
        messages=[
            {
                "role": "system",
                "content": promt
            }
        ]

        if post_text:
            messages.append(
                {"role": "user", "content": post_text}
            )
        if image_paths:
            content = [
                {"type": "text", "text": "Проанализируй эти изображения согласно инструкциям."}
            ]

            for path in image_paths:
                if path.startswith("http://") or path.startswith("https://"):
                    async with aiohttp.ClientSession() as session:
                        async with session.get(path) as resp:
                            if resp.status != 200:
                                raise Exception(f"Ошибка загрузки изображения: {path}")
                            data = await resp.read()
                            b64 = base64.b64encode(data).decode("utf-8")
                            data_uri = f"data:image/jpeg;base64,{b64}"
                else:
                    if not os.path.exists(path):
                        raise FileNotFoundError(f"Файл не найден: {path}")
                    with open(path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("utf-8")
                    data_uri = f"data:image/jpeg;base64,{b64}"

                content.append({"type": "image_url", "image_url": {"url": data_uri}})

            messages.append({"role": "user", "content": content})

        response = await cls._CLIENT.chat.completions.create(
            model=cls._MODEL,
            messages=messages,
        )
        return response.choices[0].message.content