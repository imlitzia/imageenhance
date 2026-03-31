import os
import math
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PIL import Image, ImageTk, ImageEnhance, ImageFilter, ImageOps


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
TARGET_SIZES = {
    "2K (2560x1440)": (2560, 1440),
    "4K (3840x2160)": (3840, 2160),
    "8K (7680x4320)": (7680, 4320),
}


@dataclass
class CropRect:
    x1: int = 0
    y1: int = 0
    x2: int = 0
    y2: int = 0

    def normalized(self) -> "CropRect":
        return CropRect(
            min(self.x1, self.x2),
            min(self.y1, self.y2),
            max(self.x1, self.x2),
            max(self.y1, self.y2),
        )

    def is_valid(self) -> bool:
        rect = self.normalized()
        return (rect.x2 - rect.x1) > 5 and (rect.y2 - rect.y1) > 5


class ImageEnhancerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Offline Image Crop + Upscale Tool")
        self.root.geometry("1320x860")
        self.root.minsize(1100, 760)

        self.directory: Optional[str] = None
        self.image_paths: List[str] = []
        self.current_index: int = -1
        self.original_image: Optional[Image.Image] = None
        self.preview_image: Optional[Image.Image] = None
        self.preview_photo: Optional[ImageTk.PhotoImage] = None

        self.canvas_scale: float = 1.0
        self.canvas_offset_x: int = 0
        self.canvas_offset_y: int = 0
        self.current_crop = CropRect()
        self.crop_active = False
        self.crop_box_canvas_id: Optional[int] = None

        self.output_name_var = tk.StringVar(value="enhanced_output")
        self.target_size_var = tk.StringVar(value="4K (3840x2160)")
        self.fit_mode_var = tk.StringVar(value="Contain")
        self.apply_crop_var = tk.BooleanVar(value=True)
        self.auto_contrast_var = tk.BooleanVar(value=True)
        self.sharpen_var = tk.BooleanVar(value=True)
        self.denoise_var = tk.BooleanVar(value=False)
        self.batch_mode_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Select a folder to begin.")

        self._build_ui()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)

        outer.columnconfigure(0, weight=0)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)

        # Left panel
        left = ttk.Frame(outer, width=300)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 10))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(6, weight=1)

        ttk.Label(left, text="1) Import Images", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Button(left, text="Choose Directory", command=self.choose_directory).grid(row=1, column=0, sticky="ew", pady=(6, 6))
        self.folder_label = ttk.Label(left, text="No folder selected", foreground="#555555", wraplength=280)
        self.folder_label.grid(row=2, column=0, sticky="ew", pady=(0, 10))

        ttk.Label(left, text="2) Image List", font=("Segoe UI", 11, "bold")).grid(row=3, column=0, sticky="w")
        self.listbox = tk.Listbox(left, height=14, exportselection=False)
        self.listbox.grid(row=4, column=0, sticky="nsew", pady=(6, 10))
        self.listbox.bind("<<ListboxSelect>>", self.on_listbox_select)

        nav = ttk.Frame(left)
        nav.grid(row=5, column=0, sticky="ew", pady=(0, 12))
        nav.columnconfigure((0, 1), weight=1)
        ttk.Button(nav, text="Previous", command=self.prev_image).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(nav, text="Next", command=self.next_image).grid(row=0, column=1, sticky="ew", padx=(4, 0))

        controls = ttk.LabelFrame(left, text="3) Output Settings", padding=10)
        controls.grid(row=6, column=0, sticky="nsew")
        controls.columnconfigure(1, weight=1)

        ttk.Label(controls, text="Target:").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Combobox(
            controls,
            textvariable=self.target_size_var,
            values=list(TARGET_SIZES.keys()),
            state="readonly",
        ).grid(row=0, column=1, sticky="ew", pady=4)

        ttk.Label(controls, text="Resize mode:").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Combobox(
            controls,
            textvariable=self.fit_mode_var,
            values=["Contain", "Cover"],
            state="readonly",
        ).grid(row=1, column=1, sticky="ew", pady=4)

        ttk.Label(controls, text="Output folder:").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(controls, textvariable=self.output_name_var).grid(row=2, column=1, sticky="ew", pady=4)

        ttk.Checkbutton(controls, text="Apply crop", variable=self.apply_crop_var).grid(row=3, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Checkbutton(controls, text="Auto contrast", variable=self.auto_contrast_var).grid(row=4, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Checkbutton(controls, text="Sharpen", variable=self.sharpen_var).grid(row=5, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Checkbutton(controls, text="Light denoise", variable=self.denoise_var).grid(row=6, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Checkbutton(controls, text="Batch export all images", variable=self.batch_mode_var).grid(row=7, column=0, columnspan=2, sticky="w", pady=4)

        action_row = ttk.Frame(controls)
        action_row.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        action_row.columnconfigure((0, 1), weight=1)
        ttk.Button(action_row, text="Reset Crop", command=self.reset_crop).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(action_row, text="Export", command=self.export_images).grid(row=0, column=1, sticky="ew", padx=(4, 0))

        # Right panel
        right = ttk.Frame(outer)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        header = ttk.Frame(right)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.columnconfigure(0, weight=1)
        self.image_info_label = ttk.Label(header, text="No image loaded", font=("Segoe UI", 11, "bold"))
        self.image_info_label.grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Drag on the preview to crop. Export works fully offline using Pillow.",
            foreground="#555555",
        ).grid(row=1, column=0, sticky="w")

        self.canvas = tk.Canvas(right, bg="#1f1f1f", highlightthickness=1, highlightbackground="#444444")
        self.canvas.grid(row=1, column=0, sticky="nsew")
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.canvas.bind("<Configure>", lambda event: self.refresh_preview())

        status = ttk.Label(self.root, textvariable=self.status_var, anchor="w", padding=(10, 6))
        status.pack(fill="x")

    def choose_directory(self) -> None:
        folder = filedialog.askdirectory(title="Select image directory")
        if not folder:
            return

        self.directory = folder
        self.folder_label.config(text=folder)
        self.image_paths = self.scan_images(folder)
        self.listbox.delete(0, tk.END)

        for path in self.image_paths:
            self.listbox.insert(tk.END, os.path.basename(path))

        if not self.image_paths:
            self.current_index = -1
            self.original_image = None
            self.preview_image = None
            self.canvas.delete("all")
            self.image_info_label.config(text="No supported images found")
            self.status_var.set("No supported image files were found in that directory.")
            return

        self.current_index = 0
        self.listbox.selection_set(0)
        self.listbox.activate(0)
        self.load_current_image()
        self.status_var.set(f"Loaded {len(self.image_paths)} image(s).")

    def scan_images(self, folder: str) -> List[str]:
        results = []
        for name in sorted(os.listdir(folder)):
            path = os.path.join(folder, name)
            if os.path.isfile(path) and os.path.splitext(name.lower())[1] in SUPPORTED_EXTENSIONS:
                results.append(path)
        return results

    def on_listbox_select(self, _event=None) -> None:
        selection = self.listbox.curselection()
        if not selection:
            return
        self.current_index = selection[0]
        self.load_current_image()

    def prev_image(self) -> None:
        if not self.image_paths:
            return
        self.current_index = max(0, self.current_index - 1)
        self.sync_listbox()
        self.load_current_image()

    def next_image(self) -> None:
        if not self.image_paths:
            return
        self.current_index = min(len(self.image_paths) - 1, self.current_index + 1)
        self.sync_listbox()
        self.load_current_image()

    def sync_listbox(self) -> None:
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(self.current_index)
        self.listbox.activate(self.current_index)
        self.listbox.see(self.current_index)

    def load_current_image(self) -> None:
        if not self.image_paths or self.current_index < 0:
            return

        path = self.image_paths[self.current_index]
        try:
            with Image.open(path) as img:
                self.original_image = ImageOps.exif_transpose(img).convert("RGB")
        except Exception as exc:
            messagebox.showerror("Open Error", f"Could not open image:\n{path}\n\n{exc}")
            return

        self.reset_crop(redraw=False)
        w, h = self.original_image.size
        self.image_info_label.config(text=f"{os.path.basename(path)} — {w} x {h}")
        self.refresh_preview()

    def refresh_preview(self) -> None:
        self.canvas.delete("all")
        if self.original_image is None:
            return

        canvas_w = max(1, self.canvas.winfo_width())
        canvas_h = max(1, self.canvas.winfo_height())
        img_w, img_h = self.original_image.size

        scale = min(canvas_w / img_w, canvas_h / img_h)
        disp_w = max(1, int(img_w * scale))
        disp_h = max(1, int(img_h * scale))
        self.canvas_scale = scale
        self.canvas_offset_x = (canvas_w - disp_w) // 2
        self.canvas_offset_y = (canvas_h - disp_h) // 2

        self.preview_image = self.original_image.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
        self.preview_photo = ImageTk.PhotoImage(self.preview_image)
        self.canvas.create_image(self.canvas_offset_x, self.canvas_offset_y, anchor="nw", image=self.preview_photo)

        if self.current_crop.is_valid():
            self.draw_crop_box()

    def canvas_to_image_coords(self, x: int, y: int) -> Tuple[int, int]:
        if self.original_image is None:
            return 0, 0
        img_w, img_h = self.original_image.size
        rel_x = max(0, min(x - self.canvas_offset_x, int(img_w * self.canvas_scale)))
        rel_y = max(0, min(y - self.canvas_offset_y, int(img_h * self.canvas_scale)))
        return int(rel_x / self.canvas_scale), int(rel_y / self.canvas_scale)

    def image_to_canvas_coords(self, x: int, y: int) -> Tuple[int, int]:
        cx = int(x * self.canvas_scale) + self.canvas_offset_x
        cy = int(y * self.canvas_scale) + self.canvas_offset_y
        return cx, cy

    def on_mouse_down(self, event: tk.Event) -> None:
        if self.original_image is None:
            return
        x, y = self.canvas_to_image_coords(event.x, event.y)
        self.current_crop = CropRect(x, y, x, y)
        self.crop_active = True
        self.draw_crop_box()

    def on_mouse_drag(self, event: tk.Event) -> None:
        if not self.crop_active or self.original_image is None:
            return
        x, y = self.canvas_to_image_coords(event.x, event.y)
        self.current_crop.x2 = x
        self.current_crop.y2 = y
        self.draw_crop_box()

    def on_mouse_up(self, event: tk.Event) -> None:
        if not self.crop_active:
            return
        x, y = self.canvas_to_image_coords(event.x, event.y)
        self.current_crop.x2 = x
        self.current_crop.y2 = y
        self.crop_active = False
        self.draw_crop_box()

    def draw_crop_box(self) -> None:
        if self.crop_box_canvas_id is not None:
            self.canvas.delete(self.crop_box_canvas_id)
            self.crop_box_canvas_id = None

        if not self.current_crop.is_valid():
            return

        rect = self.current_crop.normalized()
        x1, y1 = self.image_to_canvas_coords(rect.x1, rect.y1)
        x2, y2 = self.image_to_canvas_coords(rect.x2, rect.y2)
        self.crop_box_canvas_id = self.canvas.create_rectangle(
            x1, y1, x2, y2, outline="#00e5ff", width=2, dash=(5, 3)
        )

    def reset_crop(self, redraw: bool = True) -> None:
        self.current_crop = CropRect()
        self.crop_active = False
        if redraw:
            self.refresh_preview()
        else:
            if self.crop_box_canvas_id is not None:
                self.canvas.delete(self.crop_box_canvas_id)
                self.crop_box_canvas_id = None

    def apply_enhancements(self, image: Image.Image) -> Image.Image:
        result = image

        if self.denoise_var.get():
            result = result.filter(ImageFilter.MedianFilter(size=3))

        if self.auto_contrast_var.get():
            result = ImageOps.autocontrast(result)
            result = ImageEnhance.Color(result).enhance(1.05)
            result = ImageEnhance.Contrast(result).enhance(1.08)

        if self.sharpen_var.get():
            result = result.filter(ImageFilter.UnsharpMask(radius=1.8, percent=140, threshold=3))

        return result

    def crop_if_needed(self, image: Image.Image) -> Image.Image:
        if not self.apply_crop_var.get() or not self.current_crop.is_valid():
            return image
        rect = self.current_crop.normalized()
        x1, y1, x2, y2 = rect.x1, rect.y1, rect.x2, rect.y2
        return image.crop((x1, y1, x2, y2))

    def resize_to_target(self, image: Image.Image) -> Image.Image:
        target_w, target_h = TARGET_SIZES[self.target_size_var.get()]
        src_w, src_h = image.size

        if self.fit_mode_var.get() == "Cover":
            scale = max(target_w / src_w, target_h / src_h)
        else:
            scale = min(target_w / src_w, target_h / src_h)

        resized_w = max(1, int(round(src_w * scale)))
        resized_h = max(1, int(round(src_h * scale)))
        resized = image.resize((resized_w, resized_h), Image.Resampling.LANCZOS)

        if self.fit_mode_var.get() == "Cover":
            left = max(0, (resized_w - target_w) // 2)
            top = max(0, (resized_h - target_h) // 2)
            return resized.crop((left, top, left + target_w, top + target_h))

        canvas = Image.new("RGB", (target_w, target_h), (18, 18, 18))
        paste_x = (target_w - resized_w) // 2
        paste_y = (target_h - resized_h) // 2
        canvas.paste(resized, (paste_x, paste_y))
        return canvas

    def get_output_directory(self) -> str:
        assert self.directory is not None
        name = self.output_name_var.get().strip() or "enhanced_output"
        out_dir = os.path.join(self.directory, name)
        os.makedirs(out_dir, exist_ok=True)
        return out_dir

    def process_one(self, path: str) -> Tuple[bool, str]:
        try:
            with Image.open(path) as img:
                image = ImageOps.exif_transpose(img).convert("RGB")

            if path == self.image_paths[self.current_index]:
                working = self.crop_if_needed(image)
            else:
                # Batch mode uses the same crop only when requested and valid.
                working = self.crop_if_needed(image) if self.current_crop.is_valid() else image

            enhanced = self.apply_enhancements(working)
            final_image = self.resize_to_target(enhanced)

            out_dir = self.get_output_directory()
            base_name = os.path.splitext(os.path.basename(path))[0]
            suffix = self.target_size_var.get().split()[0].lower()
            out_path = os.path.join(out_dir, f"{base_name}_{suffix}.png")
            final_image.save(out_path, format="PNG", optimize=True)
            return True, out_path
        except Exception as exc:
            return False, f"{path}: {exc}"

    def export_images(self) -> None:
        if not self.image_paths or self.directory is None:
            messagebox.showwarning("No Images", "Please choose a directory with images first.")
            return

        paths = self.image_paths if self.batch_mode_var.get() else [self.image_paths[self.current_index]]
        successes = []
        failures = []

        self.root.config(cursor="watch")
        self.root.update_idletasks()

        try:
            for i, path in enumerate(paths, start=1):
                self.status_var.set(f"Processing {i}/{len(paths)}: {os.path.basename(path)}")
                self.root.update_idletasks()
                ok, result = self.process_one(path)
                if ok:
                    successes.append(result)
                else:
                    failures.append(result)
        finally:
            self.root.config(cursor="")

        if successes and not failures:
            self.status_var.set(f"Done. Exported {len(successes)} image(s).")
            messagebox.showinfo(
                "Export Complete",
                f"Successfully exported {len(successes)} image(s) to:\n{self.get_output_directory()}"
            )
        elif successes and failures:
            self.status_var.set(f"Finished with warnings. Exported {len(successes)} image(s), {len(failures)} failed.")
            messagebox.showwarning(
                "Export Finished with Warnings",
                f"Exported: {len(successes)}\nFailed: {len(failures)}\n\nOutput:\n{self.get_output_directory()}\n\nFirst error:\n{failures[0]}"
            )
        else:
            self.status_var.set("Export failed.")
            messagebox.showerror("Export Failed", failures[0] if failures else "Unknown error")


def main() -> None:
    root = tk.Tk()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    app = ImageEnhancerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
