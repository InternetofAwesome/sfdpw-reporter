
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from PIL import Image
import os
import io
import requests
from google.cloud import secretmanager
from lxml import html

project_id = 'sfdpw-413703'

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads/'

def get_authenticity_token_from_url(url):
    # Download HTML content from the URL
    response = requests.get(url)
    
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
print(get_authenticity_token_from_url('https://mobile311.sfgov.org/reports/new?service_id=518d5892601827e3880000c5'))

def submit_form_with_image(image_data):
    # Define the form fields
    form_data = {
        "utf8": "âœ“",
        "authenticity_token": "tgE8DR1LJ+Z57eVLzgFmw4doOIqq7O2n1v8hs9qhSeE=",
        "activity[definition_id]": "63c9bf3652469e4ce3043456",
        "activity[service_id]": "518d5892601827e3880000c5",
        "activity[report_id]": "",
        "address-search": "1234 Mission St, San Francisco",
        "activity[details][location][coordinates][lat]": "37.778358",
        "activity[details][location][coordinates][lng]": "-122.412041",
        "activity[details][location][address]": "1234 Mission St, San Francisco"
    }
    
    # Define the image file
    files = {
        "activity[details][photo][image]": io.BytesIO(image_data)
    }

    # Define the action URL
    url = "https://mobile311.sfgov.org/reports/new?service_id=518d5892601827e3880000c5"

    # Send the POST request
    response = requests.post(url, data=form_data, files=files)

    # Check the response
    if response.status_code == 200:
        print("Form submitted successfully!")
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
                    exif_data = img._getexif()
                    # print(f'EXIF data for {filename}: {exif_data}')
                    ll = get_lat_long_from_exif(img)
                    print(reverse_geocode(ll[0],ll[1],access_secret_version('GOOGLE_GEO_KEY')))
            except IOError:
                print(f'Error opening image file {filename}')
    return jsonify(success=True)

if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(debug=True, host='0.0.0.0', port=8080)
