#!/usr/bin/env python3
from PIL import Image
import os

try:
    LANCZOS = Image.Resampling.LANCZOS
except AttributeError:
    LANCZOS = Image.LANCZOS

LOGO_PATH = "logo.png"


def load_logo():
    if not os.path.exists(LOGO_PATH):
        raise FileNotFoundError(f"{LOGO_PATH} not found. Download it first.")
    return Image.open(LOGO_PATH).convert("RGBA")


def extract_square_icon(logo):
    w, h = logo.size
    return logo.crop((0, 0, h, h))


def create_icon(base_icon, size):
    return base_icon.resize((size, size), LANCZOS)


def create_header(base_icon, w, h):
    img = Image.new('RGB', (w, h), (255, 255, 255))
    
    icon_h = h - 8
    icon = create_icon(base_icon, icon_h)
    icon_rgb = Image.new('RGB', icon.size, (255, 255, 255))
    icon_rgb.paste(icon, mask=icon.split()[3])
    img.paste(icon_rgb, (w - icon_h - 8, 4))
    
    return img


def create_wizard(base_icon, w, h):
    img = Image.new('RGB', (w, h), (255, 255, 255))
    
    icon_size = min(w - 20, 140)
    icon = create_icon(base_icon, icon_size)
    x = (w - icon_size) // 2
    y = 40
    
    icon_rgb = Image.new('RGB', icon.size, (255, 255, 255))
    icon_rgb.paste(icon, mask=icon.split()[3])
    img.paste(icon_rgb, (x, y))
    
    return img


def main():
    print("Generating icons from logo.png...")
    
    logo = load_logo()
    base_icon = extract_square_icon(logo)
    print(f"  Extracted {base_icon.size[0]}x{base_icon.size[1]} square from logo")
    
    sizes = [16, 24, 32, 48, 64, 128, 256]
    icons = [create_icon(base_icon, s) for s in sizes]
    
    icons[-1].save('installer.ico', format='ICO', append_images=icons[:-1], sizes=[(s, s) for s in sizes])
    print(f"  installer.ico ({len(sizes)} sizes: {sizes})")
    
    create_header(base_icon, 150, 57).save('header.bmp', format='BMP')
    print("  header.bmp (150x57)")
    
    create_wizard(base_icon, 164, 314).save('wizard.bmp', format='BMP')
    print("  wizard.bmp (164x314)")
    
    print("Done!")


if __name__ == '__main__':
    main()
