
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from PIL import Image
import os
import io
import requests
from google.cloud import secretmanager
from lxml import html
from io import BytesIO

project_id = 'sfdpw-413703'
basic_data_url = 'https://mobile311.sfgov.org/reports/new?service_id=518d5892601827e3880000c5'

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads/'

def get_basic_data():
    # Download HTML content from the URL
    response = requests.get(basic_data_url)
    
    # Check if the request was successful
    if response.status_code != 200:
        print("Error:", response.status_code)
        return None
    
    # Parse the HTML content
    tree = html.fromstring(response.content)
    
    # Extract the value of the input with name="authenticity_token"
    ret = {}
    ret['authenticity_token'] = tree.xpath('//input[@name="authenticity_token"]')[0].get("value", None)
    ret['activity_definition_id'] = tree.xpath('//*[@id="activity_definition_id"]')[0].get("value", None)
    ret['activity_service_id'] = tree.xpath('//*[@id="activity_service_id"]')[0].get("value", None)
    # activity_service_id

    # input_element = tree.xpath('//input[@name="authenticity_token"]')

    
    # Check if the input element is found
    # if not input_element:
    #     print("Input element not found")
    #     return None
    
    # return input_element[0].get("value", None)
    return ret

print("auth token")
print(get_basic_data())

def submit_report(addr, img, basic_data, lat, lon):
    # Define the form fields
    form_data = {
        "utf8": "âœ“",
        "authenticity_token": basic_data["authenticity_token"],
        "activity[definition_id]": basic_data['activity_definition_id'],
        "activity[service_id]": basic_data['activity_service_id'],
        "activity[report_id]": "",
        "address-search": addr,
        "activity[details][location][coordinates][lat]": lat,
        "activity[details][location][coordinates][lng]": lon,
        "activity[details][location][address]": addr,
        "activity[details][photo][image]": "Content-Type: application/octet-stream",
        "activity[details][description]": "a bunch of crap that needs picked up",
        "activity[details][request_type]": "Other_loose_garbage_debris_yard_waste",
        "activity[details][contact][first_name]": "ButtStuff",
        "activity[details][contact][last_name]": "McGee", 
        "activity[details][contact][email]": "buttstuff@example.com",
        "activity[details][contact][phone]": "123-456-7890",
        "activity[details][contact][party_id]": ""
    }
    
    # Define the image file
    files = {
        "activity[details][photo][image]": io.BytesIO(img)
    }

    # Define the action URL
    # url = "https://mobile311.sfgov.org/reports/new?service_id=518d5892601827e3880000c5"
    url = "https://mobile311.sfgov.org/reports"

    # Send the POST request
    response = requests.post(url, data=form_data, files=files)

    # Check the response
    if response.status_code == 200:
        print("Form submitted successfully!")
        print(response.text)
    else:
        print("Error submitting form. Status code:", response.status_code)

def access_secret_version(secret_id):
    """
    Accesses a secret version from Google Cloud Secret Manager.
    """
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

def reverse_geocode(lat: float, lon: float, api_key: str) -> str:
    """
    Uses Google's Reverse Geocoding API to find the street address for a given set of coordinates.
    
    Args:
        lat (float): The latitude of the location.
        lon (float): The longitude of the location.
        api_key (str): Your Google Cloud API key with Geocoding API enabled.
    
    Returns:
        str: The most likely street address as a string, or an error message.
    """
    base_url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "latlng": f"{lat},{lon}",
        "key": access_secret_version("GOOGLE_GEO_KEY")
    }
    response = requests.get(base_url, params=params)
    if response.status_code == 200:
        results = response.json().get("results")
        if results:
            # Return the formatted address of the first result
            return results[0].get("formatted_address", "Address not found.")
        else:
            return "No results found for the given coordinates."
    else:
        return f"Error: {response.status_code}, {response.reason}"


def get_lat_long_from_exif(img):
    """Extracts latitude and longitude from an image's EXIF data.
    
    Args:
        image: An image file in memory (BytesIO object).

    Returns:
        A tuple (latitude, longitude) if coordinates are found, else None.
    """
    try:
        # Load the image using PIL
        exif_data = img._getexif()
        if not exif_data:
            return None

        # GPSInfo tag is 34853
        gps_info = exif_data.get(34853)
        if not gps_info:
            return None

        def convert_to_degrees(value):
            """Converts GPS coordinates to degrees."""
            d, m, s = value[0], value[1], value[2]
            return d + (m / 60.0) + (s / 3600.0)

        lat = gps_info.get(2)
        lat_ref = gps_info.get(1)
        lon = gps_info.get(4)
        lon_ref = gps_info.get(3)

        if lat and lon and lat_ref and lon_ref:
            lat = convert_to_degrees(lat)
            if lat_ref != 'N':
                lat = -lat
            lon = convert_to_degrees(lon)
            if lon_ref != 'E':
                lon = -lon
            return lat, lon
    except Exception as e:
        print(f"Error extracting EXIF data: {e}")
    return None

def img_convert_to_bytes(img):
    if filename != '':
        file_bytes = io.BytesIO(uploaded_file.read())
    try:
        with Image.open(file_bytes) as img:
            # Convert img to bytes
            img_byte_arr = BytesIO()
            img.save(img_byte_arr, format=img.format)
            # Now img_byte_arr.getvalue() gives you the byte representation of the image
            exif_data = img._getexif()
            ll = get_lat_long_from_exif(img)
            addr = reverse_geocode(ll[0],ll[1],access_secret_version('GOOGLE_GEO_KEY'))
            form_data = get_basic_data()
            # Pass the bytes-like object instead of the image file
            submit_report(addr, img_byte_arr.getvalue(), form_data, ll[0], ll[1])
    except IOError:
        print(f'Error opening image file {filename}')

@app.route('/')
def serve_static_index():
    return app.send_static_file('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    uploaded_files = request.files.getlist('images[]')
    print(request.files)
    print(uploaded_files)
    for uploaded_file in uploaded_files:
        filename = secure_filename(uploaded_file.filename)
        if filename != '':
            file_bytes = io.BytesIO(uploaded_file.read())
            try:
                with Image.open(file_bytes) as img:
                    # Convert img to bytes
                    img_byte_arr = BytesIO()
                    img.save(img_byte_arr, format=img.format)
                    # Now img_byte_arr.getvalue() gives you the byte representation of the image
                    exif_data = img._getexif()
                    ll = get_lat_long_from_exif(img)
                    addr = reverse_geocode(ll[0],ll[1],access_secret_version('GOOGLE_GEO_KEY'))
                    form_data = get_basic_data()
                    # Pass the bytes-like object instead of the image file
                    submit_report(addr, img_byte_arr.getvalue(), form_data, ll[0], ll[1])
            except IOError:
                print(f'Error opening image file {filename}')
    return jsonify(success=True)

if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(debug=True, host='0.0.0.0', port=8080)
