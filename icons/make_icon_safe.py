from PIL import Image

# Deschide imaginea originală (trebuie să fie în același folder)
img = Image.open("tray_icon.png")

# Conversie în RGB (elimină transparența și profilul ICC)
img = img.convert("RGB")

# Creează mai multe rezoluții standard pentru Windows
sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

# Salvează corect ca ICO multi-rezoluție
img.save("tray_icon.ico", format="ICO", sizes=sizes)

print("✅ ICO creat cu succes și compatibil Windows!")
