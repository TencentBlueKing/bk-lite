import base64
from io import BytesIO
from typing import List

import torch
from PIL import Image
from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda
from langserve import add_routes
from olmocr.prompts import build_finetuning_prompt
from olmocr.prompts.anchor import get_anchor_text

from core.user_types.ocr_request import OcrRequest
from modelscope import AutoProcessor, Qwen2VLForConditionalGeneration


class OlmOcrRunnable():
    def __init__(self):
        self.model = Qwen2VLForConditionalGeneration.from_pretrained("xhguo5/olmOCR", torch_dtype=torch.bfloat16).eval()
        self.processor = AutoProcessor.from_pretrained("xhguo5/olmOCR")
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)

    def predict(self, request: OcrRequest) -> List[Document]:
        prompt="""
        Below is the image of one page of a document, as well as some raw textual content that was previously extracted for it. 
        Just return the plain text representation of this document as if you were reading it naturally.
        Do not hallucinate.
        """
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{request.file}"}},
                ],
            }
        ]
        text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        main_image = Image.open(BytesIO(base64.b64decode(request.file)))
        inputs = self.processor(
            text=[text],
            images=[main_image],
            padding=True,
            return_tensors="pt",
        )
        inputs = {key: value.to(self.device) for (key, value) in inputs.items()}
        output = self.model.generate(
            **inputs,
            temperature=0.8,
            max_new_tokens=50,
            num_return_sequences=1,
            do_sample=True,
        )
        prompt_length = inputs["input_ids"].shape[1]
        new_tokens = output[:, prompt_length:]
        text_output = self.processor.tokenizer.batch_decode(
            new_tokens, skip_special_tokens=True
        )
        return [Document(page_content=text_output['natural_text'])]

    def register(self, app):
        add_routes(app,
                   RunnableLambda(self.predict).with_types(input_type=OcrRequest, output_type=List[Document]),
                   path='/olmocr/predict')
