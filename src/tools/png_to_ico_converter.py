from PIL import Image
import os

def convert_png_to_ico(png_path, ico_path):
    """
    Convert a PNG file to ICO format with multiple sizes.

    :param png_path: Path to the PNG file.
    :param ico_path: Path to save the ICO file.
    """
    try:
        img = Image.open(png_path)
        sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
        img.save(ico_path, format='ICO', sizes=sizes)
        print(f"ICO file saved at: {ico_path}")
    except Exception as e:
        print(f"Error converting PNG to ICO: {e}")

def convert_all_pngs_in_folder(folder_path):
    """
    Convert all PNG files in a folder to ICO format.

    :param folder_path: Path to the folder containing PNG files.
    """
    for file_name in os.listdir(folder_path):
        if file_name.lower().endswith('.png'):
            png_path = os.path.join(folder_path, file_name)
            ico_path = os.path.join(folder_path, os.path.splitext(file_name)[0] + '.ico')
            convert_png_to_ico(png_path, ico_path)

if __name__ == "__main__":
    # Example usage
    folder_path = "src/image/icon"  # Path to the folder containing PNG files

    # Ensure the folder exists
    if not os.path.exists(folder_path):
        print(f"Folder does not exist: {folder_path}")
    else:
        convert_all_pngs_in_folder(folder_path)
