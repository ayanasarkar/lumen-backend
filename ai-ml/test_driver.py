import rasterio
with rasterio.Env() as env:
    has_pds = "PDS4" in env.drivers() or "pds4" in [d.lower() for d in env.drivers()]
    print("PDS4 is Compiled:", has_pds)
    if has_pds:
        try:
            with rasterio.open("ch2_ohr_ncp_20240330T0035085365_d_img_d18.xml") as src:
                print("Successfully Opened!")
                print("Dimensions:", src.width, "x", src.height)
                print("CRS:", src.crs)
                print("Transform:", src.transform)
        except Exception as e:
            print("Failed to open XML:", e)
