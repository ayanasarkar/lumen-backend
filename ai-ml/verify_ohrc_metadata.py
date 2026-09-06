import os
import xml.etree.ElementTree as ET
import rasterio

xml_path = "ch2_ohr_ncp_20240330T0035085365_d_img_d18.xml"
img_path = "ch2_ohr_ncp_20240330T0035085365_d_img_d18.img"

print("=" * 60)
print("EXTRACTING CHANDRAYAAN-2 OHRC XML LABELS")
print("=" * 60)

if not os.path.exists(xml_path):
    print(f"Error: {xml_path} not found.")
else:
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        def strip_ns(tag):
            return tag.split('}')[-1] if '}' in tag else tag
            
        print("\nScanning XML for geographical, solar, and sensor parameters:")
        found_any = False
        for elem in root.iter():
            tag_clean = strip_ns(elem.tag).lower()
            match_keywords = [
                "latitude", "longitude", "incidence", "solar", "sun", 
                "azimuth", "elevation", "phase", "emission", "corner", 
                "bounding", "geographic", "point", "coordinate", "roll", 
                "pitch", "yaw", "orbit"
            ]
            if any(k in tag_clean for k in match_keywords):
                text = elem.text.strip() if elem.text else ""
                if text:
                    print(f"  <{strip_ns(elem.tag)}> : {text}")
                    found_any = True
        if not found_any:
            print("No matching spatial tags found in XML.")
    except Exception as e:
        print(f"Error parsing XML with ElementTree: {e}")
        print("Falling back to raw text-line search:")
        with open(xml_path, "r", encoding="utf-8") as f:
            for line in f:
                line_lower = line.lower()
                if any(k in line_lower for k in ["lat", "lon", "sun", "azimuth", "elevation", "incidence", "bounding"]):
                    print(f"  {line.strip()}")

print("\n" + "=" * 60)
print("CHECKING NATIVE GEOTRANSFORM & CRS IN IMG")
print("=" * 60)

if not os.path.exists(img_path):
    print(f"Error: {img_path} not found.")
else:
    try:
        with rasterio.open(img_path) as src:
            print("Rasterio opened file cleanly: YES")
            print(f"Image Dimensions            : {src.width} x {src.height}")
            print(f"Number of Bands             : {src.count}")
            print(f"Data Type                   : {src.dtypes[0]}")
            print(f"Coordinate Reference System : {src.crs}")
            print(f"Affine Transform Matrix     : {src.transform}")
            print(f"Is Transform Identity?      : {src.transform.is_identity}")
            
            if src.transform.is_identity:
                print("\n[VERDICT] The Geotransform is the IDENTITY matrix, and CRS is None.")
                print("This confirms the binary file possesses NO native georeferencing info.")
    except Exception as e:
        print(f"Rasterio opened file cleanly: NO (Error: {e})")
