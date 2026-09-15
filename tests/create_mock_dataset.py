import os
import shutil
import pandas as pd
from PIL import Image
import piexif
from geopy.distance import geodesic

def decimal_to_dms(decimal):
    """Convert decimal degrees to degrees, minutes, seconds tuple for EXIF."""
    degrees = int(decimal)
    minutes_float = abs(decimal - degrees) * 60
    minutes = int(minutes_float)
    seconds_float = (minutes_float - minutes) * 60

    return ((abs(degrees), 1), (minutes, 1), (int(seconds_float * 1000000), 1000000))

def create_image_with_gps(filename, lat, lon):
    """Create a blank JPEG and insert GPS EXIF data."""
    img = Image.new('RGB', (100, 100), color = 'red')
    img.save(filename)

    if lat is not None and lon is not None:
        lat_ref = "N" if lat >= 0 else "S"
        lon_ref = "E" if lon >= 0 else "W"

        gps_ifd = {
            piexif.GPSIFD.GPSLatitudeRef: lat_ref,
            piexif.GPSIFD.GPSLatitude: decimal_to_dms(lat),
            piexif.GPSIFD.GPSLongitudeRef: lon_ref,
            piexif.GPSIFD.GPSLongitude: decimal_to_dms(lon),
        }

        exif_dict = {"0th": {}, "Exif": {}, "GPS": gps_ifd, "1st": {}, "thumbnail": None}
        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, filename)

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    mock_dir = os.path.join(base_dir, "mock_data")
    excel_dir = os.path.join(mock_dir, "excel")
    photo_dir = os.path.join(mock_dir, "photos")
    output_dir = os.path.join(mock_dir, "output")

    # Clean up and recreate directories
    for d in [excel_dir, photo_dir, output_dir]:
        if os.path.exists(d):
            shutil.rmtree(d)
        os.makedirs(d)

    # 1. Mock Excel Files
    # Point 1
    p1_lat, p1_lon = 24.498533, 54.375940

    # Point 2: Close to Point 1 (around 60 meters away)
    # 1 degree of latitude is ~111,320 meters. 60m is approx 60 / 111320 = 0.000539 degrees
    p2_lat = p1_lat + 0.000539
    p2_lon = p1_lon

    # Point 3: Independent point far away
    p3_lat, p3_lon = 24.550000, 54.400000

    # Point 4: Duplicate of Point 1
    p4_lat, p4_lon = p1_lat, p1_lon

    # Create points_part1.xlsx
    df1 = pd.DataFrame([
        {"point_name": "Point_1", "latitude": p1_lat, "longitude": p1_lon, "altitude": 10, "north": 0, "east": 0, "Recorded at": "2023-01-01"},
        {"point_name": "Point_2", "latitude": p2_lat, "longitude": p2_lon, "altitude": 10, "north": 0, "east": 0, "Recorded at": "2023-01-01"}
    ])
    df1.to_excel(os.path.join(excel_dir, "points_part1.xlsx"), index=False)

    # Create points_part2.xlsx
    df2 = pd.DataFrame([
        {"point_name": "Point_3", "latitude": p3_lat, "longitude": p3_lon, "altitude": 20, "north": 0, "east": 0, "Recorded at": "2023-01-02"},
        {"point_name": "Point_1", "latitude": p4_lat, "longitude": p4_lon, "altitude": 10, "north": 0, "east": 0, "Recorded at": "2023-01-01"} # Duplicate
    ])
    df2.to_excel(os.path.join(excel_dir, "points_part2.xlsx"), index=False)

    # 2. Mock Images with EXIF GPS
    # Image A: 10m from Point 1 (should match Point 1 only)
    img_a_lat = p1_lat + (10 / 111320.0)
    img_a_lon = p1_lon
    create_image_with_gps(os.path.join(photo_dir, "Image_A.jpg"), img_a_lat, img_a_lon)

    # Image B: Exactly in the overlapping 50m zone of both Point 1 and Point 2
    # Midpoint between P1 and P2 is 30m from each
    img_b_lat = (p1_lat + p2_lat) / 2
    img_b_lon = p1_lon
    create_image_with_gps(os.path.join(photo_dir, "Image_B.jpg"), img_b_lat, img_b_lon)

    # Image C: 500m away from all points (should land in Inconnect_photo)
    img_c_lat = p1_lat + (500 / 111320.0)
    img_c_lon = p1_lon
    create_image_with_gps(os.path.join(photo_dir, "Image_C.jpg"), img_c_lat, img_c_lon)

    # Image D: No GPS tags injected (should land in Inconnect_photo/No_GPS)
    create_image_with_gps(os.path.join(photo_dir, "Image_D.jpg"), None, None)

    # Image E: 15m from Point 3 (should match Point 3)
    img_e_lat = p3_lat + (15 / 111320.0)
    img_e_lon = p3_lon
    create_image_with_gps(os.path.join(photo_dir, "Image_E.jpg"), img_e_lat, img_e_lon)

    print("Mock dataset generated successfully in 'tests/mock_data/'")
    print("\nTo run the main tool against this mock dataset, use the following command:")
    print("python src/gcp_processor.py --excel_dir tests/mock_data/excel --photo_dir tests/mock_data/photos --output_dir tests/mock_data/output --buffer_distance 50.0")

if __name__ == "__main__":
    main()
