"""Temporary Gemini SDK diagnostic — run: python diagnose_gemini.py"""
import sys

import google.generativeai as genai

from app.utils.config import get_settings


def main() -> int:
    settings = get_settings()

    print("=== SDK ===")
    print(f"Package: google.generativeai")
    print(f"Version: {getattr(genai, '__version__', 'unknown')}")
    print(f"google.genai installed: ", end="")
    try:
        import google.genai  # noqa: F401
        print("yes")
    except ImportError:
        print("no")

    print("\n=== CONFIG ===")
    print(f"LLM_MODEL (env): {settings.LLM_MODEL}")
    print(f"GOOGLE_LLM_MODEL: {settings.GOOGLE_LLM_MODEL}")
    print(f"GOOGLE_API_KEY set: {bool(settings.GOOGLE_API_KEY)}")

    if not settings.GOOGLE_API_KEY:
        print("ERROR: GOOGLE_API_KEY missing")
        return 1

    genai.configure(api_key=settings.GOOGLE_API_KEY)

    print("\n=== AVAILABLE MODELS (generateContent) ===")
    generation_models = []
    try:
        for model in genai.list_models():
            methods = getattr(model, "supported_generation_methods", []) or []
            if "generateContent" in methods:
                generation_models.append(model.name)
                print(f"  {model.name}")
    except Exception as exc:
        print(f"ERROR listing models: {exc}")
        return 1

    configured = settings.LLM_MODEL
    configured_full = configured if configured.startswith("models/") else f"models/{configured}"

    print("\n=== CONFIGURED MODEL CHECK ===")
    print(f"Configured: {configured}")
    print(f"Full name:  {configured_full}")
    print(f"In list_models(): {configured_full in generation_models}")

    print("\n=== GENERATION TEST ===")
    for name in [configured, configured_full.replace("models/", "")]:
        print(f"\nTrying GenerativeModel({name!r})...")
        try:
            client = genai.GenerativeModel(name)
            response = client.generate_content("Reply with exactly: OK")
            text = getattr(response, "text", str(response))
            print(f"  SUCCESS: {text[:80]!r}")
        except Exception as exc:
            print(f"  FAILED: {type(exc).__name__}: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
