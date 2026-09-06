# download_ref.py
import urllib.request
import xml.etree.ElementTree as ET
import os

def download_overlapping_nasa_image():
    print("=" * 60)
    print("AUTOMATED LRO NAC SEARCH & DOWNLOAD VIA ODE REST API")
    print("=" * 60)
    
    # Define your coordinates from QGIS
    # Bounding box centered around Lat: 3.64, Lon: -2.46 (357.54 East)
    params = {
        "target": "moon",
        "query": "products",
        "results": "p",          # 'p' returns full product metadata and file URLs
        "iid": "LROC",
        "pt": "CDRNAC",         # CDR Narrow Angle Camera (calibrated)
        "minlat": "3.4",
        "maxlat": "3.8",
        "westernlon": "357.3",
        "easternlon": "357.7"
    }
    
    # Construct the WashU ODE REST API request URL
    api_base = "https://oderest.rsl.wustl.edu/live2?"
    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    request_url = api_base + query_string
    
    print(f"Connecting to NASA/PDS database...\nURL: {request_url}\n")
    
    try:
        # Send HTTP GET request to the REST API
        headers = {'User-Agent': 'Mozilla/5.0'}
        req = urllib.request.Request(request_url, headers=headers)
        with urllib.request.urlopen(req) as response:
            xml_data = response.read()
            
        # Parse XML response
        root = ET.fromstring(xml_data)
        
        # Search the XML structure for matching products and their files
        products = root.findall(".//Product")
        if not products:
            print("No matching LRO NAC images found in this coordinate box.")
            return
            
        print(f"Found {len(products)} overlapping LRO NAC products.")
        
        # We will pick the first product and look for its GeoTIFF file
        target_product = products[0]
        product_id = target_product.find("ProductID").text
        print(f"Selected Product ID for download: {product_id}")
        
        # Search for file URLs in the metadata
        file_elements = target_product.findall(".//ProductFile")
        download_url = None
        file_name = None
        
        for f in file_elements:
            url_text = f.find("URL").text
            # Look specifically for the map-projected high-contrast GeoTIFF file
            if url_text.endswith(".TIF") or url_text.endswith(".tiff"):
                download_url = url_text
                file_name = f.find("FileName").text
                break
                
        if download_url:
            output_path = os.path.join(os.getcwd(), "nasa_ref.tif")
            print(f"Found GeoTIFF URL: {download_url}")
            print(f"Downloading file as 'nasa_ref.tif' (this may take a moment)...")
            
            # Download and save the file
            urllib.request.urlretrieve(download_url, output_path)
            print(f"✅ Success! File downloaded and saved to: {output_path}")
        else:
            print("Error: No GeoTIFF format file (.TIF) was found in the product metadata.")
            
    except Exception as e:
        print(f"An error occurred during search or download: {e}")
        print("Please check your internet connection or verify the coordinate values.")

if __name__ == "__main__":
    download_overlapping_nasa_image()