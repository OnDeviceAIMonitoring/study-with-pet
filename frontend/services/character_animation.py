"""Character animation loading helpers shared by personal/group study."""

import os

import customtkinter as ctk
from PIL import Image


def _build_ctk_image(img_path, target_w, target_h):
    pil_img = Image.open(img_path).convert("RGBA")
    bg = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    pil_img.thumbnail((target_w, target_h), Image.LANCZOS)
    ox = (target_w - pil_img.width) // 2
    oy = (target_h - pil_img.height) // 2
    bg.paste(pil_img, (ox, oy), pil_img)
    return ctk.CTkImage(light_image=bg, dark_image=bg, size=(target_w, target_h))


def load_character_animation_sets(
    char_name,
    char_type,
    target_w=120,
    target_h=None,
    anim_names=("happy", "tail", "tear"),
    tear_fallback_to_sad=False,
):
    if target_h is None:
        target_h = int(target_w * 650 / 430)

    anim_sets = {}
    for anim_name in anim_names:
        anim_dir = f"frontend/assets/characters/{char_name}/{char_type}/{anim_name}"
        if anim_name == "tear" and tear_fallback_to_sad and not os.path.isdir(anim_dir):
            anim_dir = f"frontend/assets/characters/{char_name}/{char_type}/sad"

        frames = []
        if os.path.isdir(anim_dir):
            files = sorted([f for f in os.listdir(anim_dir) if f.endswith(".png")])
            for fn in files:
                try:
                    ctk_img = _build_ctk_image(os.path.join(anim_dir, fn), target_w, target_h)
                    frames.append(ctk_img)
                except Exception:
                    continue
        anim_sets[anim_name] = frames

    return anim_sets
