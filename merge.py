import os
import shutil
import json5
import piexif
import subprocess
from tqdm import tqdm
from datetime import datetime
from pathlib import Path

# 📂 Configura i percorsi
home = os.path.expanduser("~")
takeout_root = os.path.join(home, "Scaricati")
output_root = os.path.join(takeout_root, "GoogleFotoUnificati")
os.makedirs(output_root, exist_ok=True)

# 📸 Estensioni supportate
image_exts = {".jpg", ".jpeg", ".png"}
video_exts = {".mp4", ".mov", ".avi", ".mkv"}
media_exts = image_exts.union(video_exts)

# 🔁 Conversione coordinate GPS
def convert_gps(coord):
    deg = int(coord)
    min_float = abs((coord - deg) * 60)
    min = int(min_float)
    sec = int((min_float - min) * 60 * 10000)
    return ((deg,1), (min,1), (sec,10000))

# 🖼️ Scrittura metadati immagini
def write_image_metadata(img_path, metadata):
    try:
        exif_dict = piexif.load(img_path)

        if "photoTakenTime" in metadata and "timestamp" in metadata["photoTakenTime"]:
            ts = int(metadata["photoTakenTime"]["timestamp"])
            dt_str = datetime.utcfromtimestamp(ts).strftime("%Y:%m:%d %H:%M:%S")
            exif_dict['Exif'][piexif.ExifIFD.DateTimeOriginal] = dt_str.encode()
            exif_dict['0th'][piexif.ImageIFD.DateTime] = dt_str.encode()

        if "description" in metadata:
            exif_dict['0th'][piexif.ImageIFD.ImageDescription] = metadata["description"].encode()

        if "geoData" in metadata:
            gps = metadata["geoData"]
            if gps.get("latitude") and gps.get("longitude"):
                lat = gps["latitude"]
                lon = gps["longitude"]
                exif_dict['GPS'][piexif.GPSIFD.GPSLatitudeRef] = b'N' if lat >= 0 else b'S'
                exif_dict['GPS'][piexif.GPSIFD.GPSLatitude] = convert_gps(abs(lat))
                exif_dict['GPS'][piexif.GPSIFD.GPSLongitudeRef] = b'E' if lon >= 0 else b'W'
                exif_dict['GPS'][piexif.GPSIFD.GPSLongitude] = convert_gps(abs(lon))

        piexif.insert(piexif.dump(exif_dict), img_path)
    except Exception as e:
        print(f"❌ Errore metadata immagine {img_path}: {e}")

# 🎥 Scrittura metadati video via exiftool
def write_video_metadata(vid_path, metadata):
    cmd = ["exiftool", "-overwrite_original"]
    if "photoTakenTime" in metadata and "timestamp" in metadata["photoTakenTime"]:
        dt = datetime.utcfromtimestamp(int(metadata["photoTakenTime"]["timestamp"])).strftime("%Y:%m:%d %H:%M:%S")
        cmd += [f"-CreateDate={dt}", f"-MediaCreateDate={dt}", f"-ModifyDate={dt}"]
    if "description" in metadata:
        cmd.append(f"-Description={metadata['description']}")
    cmd.append(vid_path)
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# 🔍 Cerca tutte le cartelle "Google Foto" ricorsivamente
google_foto_paths = list(Path(takeout_root).rglob("Google Foto"))
if not google_foto_paths:
    print("⚠️ Nessuna cartella 'Google Foto' trovata.")
    exit(1)

# 📦 Scansione file media
for google_photos in google_foto_paths:
    print(f"\n📁 Elaboro: {google_photos}")

    for album in os.listdir(google_photos):
        src_album = os.path.join(google_photos, album)
        dst_album = os.path.join(output_root, album)
        os.makedirs(dst_album, exist_ok=True)

        if not os.path.isdir(src_album):
            continue

        for filename in tqdm(os.listdir(src_album), desc=f"{album}"):
            src_file = os.path.join(src_album, filename)
            if not os.path.isfile(src_file):
                continue

            name, ext = os.path.splitext(filename)
            ext = ext.lower()

            if ext in media_exts:
                # ✏️ Gestione duplicati
                dst_file = os.path.join(dst_album, filename)
                counter = 1
                while os.path.exists(dst_file):
                    dst_file = os.path.join(dst_album, f"{name}_{counter}{ext}")
                    counter += 1

                shutil.copy2(src_file, dst_file)

                # 📑 Cerca JSON metadati associato
                json_file = os.path.join(src_album, filename + ".json")
                if os.path.exists(json_file):
                    try:
                        with open(json_file, "r", encoding="utf-8") as f:
                            metadata = json5.load(f)

                        if ext in image_exts:
                            write_image_metadata(dst_file, metadata)
                        elif ext in video_exts:
                            write_video_metadata(dst_file, metadata)

                        os.remove(json_file)
                        print(f"✔️ Metadati inseriti e JSON rimosso: {dst_file}")
                    except Exception as e:
                        print(f"❌ Errore metadati {filename}: {e}")

            elif ext == ".json":
                continue  # già gestito

            else:
                # ➕ Altri file (copiati così come sono)
                shutil.copy2(src_file, os.path.join(dst_album, filename))

print("\n🎉 Completato! File unificati, metadati scritti e .json eliminati.")
