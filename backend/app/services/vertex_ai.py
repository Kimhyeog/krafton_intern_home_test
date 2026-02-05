import vertexai
from vertexai.preview.vision_models import ImageGenerationModel
from google.cloud import aiplatform
from app.config import get_settings
import aiofiles
import os
import asyncio
import base64

settings = get_settings()
vertexai.init(project=settings.google_cloud_project, location=settings.google_cloud_region)

VEO_MODEL = "veo-3.0-fast-generate-001"
IMAGEN_MODEL = "imagen-3.0-fast-generate-001"

class VertexAIService:
    def __init__(self):
        self.image_model = ImageGenerationModel.from_pretrained(IMAGEN_MODEL)
        self.client = aiplatform.gapic.PredictionServiceClient(
            client_options={"api_endpoint": f"{settings.google_cloud_region}-aiplatform.googleapis.com"}
        )
        self.project = settings.google_cloud_project
        self.location = settings.google_cloud_region

    async def generate_image(self, prompt: str, job_id: str) -> str:
        """Text-to-Image: Imagen 3.0으로 이미지 생성"""
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.image_model.generate_images(
                prompt=prompt,
                number_of_images=1
            )
        )

        file_name = f"{job_id}.png"
        file_path = os.path.join(settings.storage_path, "images", file_name)

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(response.images[0]._image_bytes)

        return f"/storage/images/{file_name}"

    async def generate_video_from_text(self, prompt: str, job_id: str) -> str:
        """Text-to-Video: Veo 3.0으로 텍스트에서 비디오 생성"""
        endpoint = f"projects/{self.project}/locations/{self.location}/publishers/google/models/{VEO_MODEL}"

        request = {
            "instances": [{"prompt": prompt}],
            "parameters": {"sampleCount": 1}
        }

        loop = asyncio.get_event_loop()
        operation = await loop.run_in_executor(
            None,
            lambda: self.client.predict(
                endpoint=endpoint,
                instances=request["instances"],
                parameters=request["parameters"]
            )
        )

        video_bytes = await self._extract_video(operation)

        file_name = f"{job_id}.mp4"
        file_path = os.path.join(settings.storage_path, "videos", file_name)

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(video_bytes)

        return f"/storage/videos/{file_name}"

    async def generate_video_from_image(self, prompt: str, image_bytes: bytes, job_id: str) -> str:
        """Image-to-Video: Veo 3.0으로 이미지에서 비디오 생성"""
        endpoint = f"projects/{self.project}/locations/{self.location}/publishers/google/models/{VEO_MODEL}"

        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        request = {
            "instances": [{
                "prompt": prompt,
                "image": {"bytesBase64Encoded": image_base64}
            }],
            "parameters": {"sampleCount": 1}
        }

        loop = asyncio.get_event_loop()
        operation = await loop.run_in_executor(
            None,
            lambda: self.client.predict(
                endpoint=endpoint,
                instances=request["instances"],
                parameters=request["parameters"]
            )
        )

        video_bytes = await self._extract_video(operation)

        file_name = f"{job_id}.mp4"
        file_path = os.path.join(settings.storage_path, "videos", file_name)

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(video_bytes)

        return f"/storage/videos/{file_name}"

    async def _extract_video(self, operation) -> bytes:
        """응답에서 비디오 바이트 추출"""
        if hasattr(operation, 'predictions') and operation.predictions:
            prediction = operation.predictions[0]
            if 'bytesBase64Encoded' in prediction:
                return base64.b64decode(prediction['bytesBase64Encoded'])
            elif 'video' in prediction and 'bytesBase64Encoded' in prediction['video']:
                return base64.b64decode(prediction['video']['bytesBase64Encoded'])
        raise Exception("Failed to extract video from response")

vertex_ai_service = VertexAIService()
