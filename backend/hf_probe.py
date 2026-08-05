"""List the API endpoints exposed by HF_SPACE.

hf_client.py guesses endpoint names ("/preprocess_image", "/image_to_3d",
"/extract_glb") from the reference TRELLIS app. If HF_SPACE is a fork that
renamed its functions, generation will fail with an unknown-api-name error.
Run this to see what the Space actually calls things, then set HF_API_NAME
(the generation step) accordingly:

    python -m backend.hf_probe
"""
from gradio_client import Client

from .config import HF_SPACE, HF_TOKEN


def main() -> None:
    print(f"Probing {HF_SPACE} ...")
    client = Client(HF_SPACE, token=HF_TOKEN or None)
    client.view_api()


if __name__ == "__main__":
    main()
