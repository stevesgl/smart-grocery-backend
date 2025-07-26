import os
import json
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv # For loading environment variables

# Import Vertex AI specific libraries
import vertexai
from vertexai.generative_models import GenerativeModel, Part, Image

# Load environment variables from .env file.
# This should be called as early as possible to make environment variables available.
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Enable CORS for all origins, allowing your frontend to connect.
# In a production environment, you would restrict this to specific origins for security.
CORS(app)

# Initialize Vertex AI with your project ID and location.
# It's highly recommended to load these from environment variables for security and flexibility.
# Ensure your .env file contains GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION.
try:
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION")
    if not project_id or not location:
        # If environment variables are not set, print a warning but don't exit.
        # This allows the app to run, but Vertex AI related endpoints will fail.
        print("Warning: GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION environment variables are not set.")
        print("Vertex AI functionality will not be available.")
        vertex_ai_initialized = False
    else:
        vertexai.init(project=project_id, location=location)
        # Initialize the GenerativeModel for text and multimodal content
        # We will use 'gemini-1.5-flash-001' as it's a good general-purpose model.
        # If you need specific capabilities, you can change this model.
        # This model instance will be used for text generation and image understanding.
        gemini_flash_model = GenerativeModel("gemini-1.5-flash-001")
        imagen_model = GenerativeModel("imagen-3.0-generate-002") # Model for image generation
        print(f"Vertex AI initialized successfully for project: {project_id}, location: {location}")
        vertex_ai_initialized = True
except Exception as e:
    print(f"Error initializing Vertex AI: {e}")
    vertex_ai_initialized = False

# --- Configuration and Data Loading ---
# Define paths for ingredient data files
# These paths are relative to the directory where app.py is run.
INGREDIENTS_FILE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'common_ingredients_live.json')
STRUCTURED_INGREDIENTS_FILE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'structured_common_ingredients_live.json')

# Global variables to store loaded data
common_ingredients_set = set()
structured_common_ingredients = []

def load_json_data(file_path):
    """
    Loads JSON data from a specified file path.
    Returns the loaded data or None if an error occurs.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found at {file_path}")
        return None
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {file_path}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while loading {file_path}: {e}")
        return None

# Load ingredient data on application startup
# It's crucial that these files are in the specified 'data' directory
# relative to your backend folder.
loaded_common_ingredients = load_json_data(INGREDIENTS_FILE_PATH)
if loaded_common_ingredients:
    common_ingredients_set = set(loaded_common_ingredients)
    print(f"Loaded {len(common_ingredients_set)} common ingredients.")
else:
    print("Failed to load common_ingredients_live.json. Application may not function correctly.")

loaded_structured_ingredients = load_json_data(STRUCTURED_INGREDIENTS_FILE_PATH)
if loaded_structured_ingredients:
    structured_common_ingredients = loaded_structured_ingredients
    print(f"Loaded {len(structured_common_ingredients)} structured common ingredients.")
else:
    print("Failed to load structured_common_ingredients_live.json. Application may not function correctly.")

# --- Ingredient Parsing Integration ---
# Import the ingredient_parser module.
# Ensure ingredient_parser.py is in the same directory as app.py,
# or in a directory included in your Python path.
try:
    from ingredient_parser import parse_ingredient_string
    print("Successfully imported ingredient_parser.")
except ImportError:
    print("Error: Could not import ingredient_parser. Make sure 'ingredient_parser.py' is in the correct directory.")
    # Exit or handle gracefully if the core module is missing
    # For now, we'll just print the error and let the app continue, though this endpoint will fail.


# --- Routes ---

@app.route('/')
def index():
    """
    A simple root endpoint to confirm the API is running.
    Returns a JSON message indicating the API status.
    """
    return jsonify({"message": "Gemini API backend is running!"}), 200

@app.route('/check_ingredients_loaded')
def check_ingredients_loaded():
    """
    Endpoint to check if ingredient data has been loaded successfully.
    """
    return jsonify({
        "common_ingredients_loaded": bool(common_ingredients_set),
        "structured_ingredients_loaded": bool(structured_common_ingredients)
    })

@app.route('/parse_ingredient', methods=['POST'])
def parse_ingredient():
    """
    Endpoint to parse a single ingredient string using the ingredient_parser.
    Expects a JSON payload with 'ingredient_string' and 'common_ingredients_set'.
    """
    # Check if ingredient_parser was successfully imported
    if 'parse_ingredient_string' not in globals():
        return jsonify({"error": "Ingredient parser not available. Check server logs."}), 500

    data = request.get_json()
    if not data or 'ingredient_string' not in data:
        return jsonify({"error": "Missing 'ingredient_string' in request body"}), 400

    ingredient_string = data['ingredient_string']
    # Use the globally loaded common_ingredients_set
    # If the client sends a common_ingredients_set, it will override the global one for this request.
    # This allows for flexibility if the client has a more up-to-date set.
    request_common_ingredients_set = set(data.get('common_ingredients_set', []))
    if not request_common_ingredients_set:
        request_common_ingredients_set = common_ingredients_set

    try:
        parsed_data = parse_ingredient_string(ingredient_string, request_common_ingredients_set)
        return jsonify(parsed_data)
    except Exception as e:
        print(f"Error parsing ingredient: {e}")
        return jsonify({"error": f"Failed to parse ingredient: {str(e)}"}), 500

@app.route('/search_ingredient', methods=['POST'])
def search_ingredient():
    """
    Endpoint to search through the structured common ingredients.
    Expects a JSON payload with a 'query' string.
    Performs a case-insensitive search on the 'base_ingredient' field.
    """
    data = request.get_json()
    if not data or 'query' not in data:
        return jsonify({"error": "Missing 'query' in request body"}), 400

    search_query = data['query'].lower()
    results = []

    # Iterate through structured_common_ingredients and find matches
    # This is a simple substring search for demonstration.
    # For larger datasets, consider more optimized search solutions (e.g., indexing).
    for ingredient in structured_common_ingredients:
        # Ensure 'base_ingredient' exists and is a string before attempting to lower()
        if 'base_ingredient' in ingredient and isinstance(ingredient['base_ingredient'], str):
            if search_query in ingredient['base_ingredient'].lower():
                results.append(ingredient)

    return jsonify(results)

@app.route('/generate_image', methods=['POST'])
def generate_image():
    """
    Endpoint to generate an image using the Imagen 3.0 model.
    Expects a JSON payload with a 'prompt' string.
    Returns a base64 encoded image URL.
    """
    if not vertex_ai_initialized:
        return jsonify({"error": "Vertex AI not initialized. Check server configuration."}), 500

    data = request.get_json()
    if not data or 'prompt' not in data:
        return jsonify({"error": "Missing 'prompt' in request body"}), 400

    prompt = data['prompt']

    try:
        # Use the pre-initialized imagen_model
        response = imagen_model.generate_content(prompt)

        if response.candidates and len(response.candidates) > 0 and \
           response.candidates[0].content and \
           response.candidates[0].content.parts and \
           len(response.candidates[0].content.parts) > 0:
            # Assuming the first part is the image data
            image_part = response.candidates[0].content.parts[0]
            if image_part.inline_data and image_part.inline_data.mime_type.startswith('image/'):
                base64_image = image_part.inline_data.data
                image_url = f"data:{image_part.inline_data.mime_type};base64,{base64_image}"
                return jsonify({"imageUrl": image_url})
            else:
                return jsonify({"error": "Generated content is not an image or is malformed."}), 500
        else:
            return jsonify({"error": "Image generation failed or returned no image data."}), 500
    except Exception as e:
        print(f"Error generating image: {e}")
        return jsonify({"error": f"Failed to generate image: {str(e)}"}), 500


@app.route('/generate_text', methods=['POST'])
def generate_text():
    """
    Endpoint to generate text using the Gemini 2.0 Flash model.
    Expects a JSON payload with a 'prompt' string.
    Returns the generated text.
    """
    if not vertex_ai_initialized:
        return jsonify({"error": "Vertex AI not initialized. Check server configuration."}), 500

    data = request.get_json()
    if not data or 'prompt' not in data:
        return jsonify({"error": "Missing 'prompt' in request body"}), 400

    prompt = data['prompt']

    try:
        # Use the pre-initialized gemini_flash_model
        response = gemini_flash_model.generate_content(prompt)

        if response.text:
            return jsonify({"generated_text": response.text})
        else:
            return jsonify({"error": "Text generation failed or returned no text data"}), 500
    except Exception as e:
        print(f"Error generating text: {e}")
        return jsonify({"error": f"Failed to generate text: {str(e)}"}), 500


@app.route('/understand_image', methods=['POST'])
def understand_image():
    """
    Handles image understanding requests.
    Expects a POST request with 'image' (file) and 'prompt' (string) in the form data.
    Uses the Gemini model to analyze the image based on the provided prompt and returns the text response.
    """
    if not vertex_ai_initialized:
        return jsonify({"error": "Vertex AI not initialized. Check server configuration."}), 500

    if 'image' not in request.files:
        return jsonify({"error": "No image file provided"}), 400
    if 'prompt' not in request.form:
        return jsonify({"error": "No prompt provided"}), 400

    image_file = request.files['image']
    prompt_text = request.form['prompt']

    if image_file.filename == '':
        return jsonify({"error": "No selected image file"}), 400

    try:
        image_data = image_file.read()
        image_part = Part.from_data(data=image_data, mime_type=image_file.mimetype)

        # Use the pre-initialized gemini_flash_model
        contents = [prompt_text, image_part]
        response = gemini_flash_model.generate_content(contents)

        generated_text = response.text
        return jsonify({"response": generated_text})

    except Exception as e:
        print(f"Error during image understanding: {e}")
        return jsonify({"error": f"An error occurred during image understanding: {str(e)}"}), 500


@app.route('/structured_response', methods=['POST'])
def structured_response():
    """
    Endpoint to get a structured response (JSON) from the Gemini 2.0 Flash model.
    Expects a JSON payload with a 'prompt' string.
    Returns a JSON object based on the defined responseSchema.
    """
    if not vertex_ai_initialized:
        return jsonify({"error": "Vertex AI not initialized. Check server configuration."}), 500

    data = request.get_json()
    if not data or 'prompt' not in data:
        return jsonify({"error": "Missing 'prompt' in request body"}), 400

    prompt = data['prompt']

    # Define the generation configuration for structured output
    generation_config = {
        "responseMimeType": "application/json",
        "responseSchema": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "original_string": {"type": "STRING"},
                    "base_ingredient": {"type": "STRING"},
                    "modifiers": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "attributes": {
                        "type": "OBJECT",
                        "properties": {
                            "ingredient_type": {"type": "STRING"},
                            "trust_report_category": {"type": "STRING"}
                        }
                    },
                    "parenthetical_info": {"type": "OBJECT"},
                    "unusual_punctuation_found": {"type": "ARRAY", "items": {"type": "STRING"}}
                },
                "propertyOrdering": [
                    "original_string", "base_ingredient", "modifiers",
                    "attributes", "parenthetical_info", "unusual_punctuation_found"
                ]
            }
        }
    }

    try:
        # Use the pre-initialized gemini_flash_model
        response = gemini_flash_model.generate_content(
            contents=[{"role": "user", "parts": [{"text": prompt}]}],
            generation_config=generation_config
        )

        if response.text:
            parsed_json_str = response.text
            parsed_data = json.loads(parsed_json_str)
            return jsonify({"parsedIngredients": parsed_data})
        else:
            return jsonify({"error": "Structured response failed or returned no data"}), 500
    except json.JSONDecodeError as e:
        print(f"JSON decoding error: {e}")
        return jsonify({"error": f"Invalid JSON response from model: {str(e)}"}), 500
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500


@app.errorhandler(500)
def internal_server_error(e):
    """
    Global error handler for 500 Internal Server Errors.
    This catches any unhandled exceptions in the application and returns a standardized JSON error response.
    """
    # Log the exception for debugging purposes.
    # Using app.logger.error requires proper Flask logging setup, for simplicity, using print for now.
    print(f"Internal Server Error: {e}")
    return jsonify({"error": "An unexpected error occurred. Please try again later.", "details": str(e)}), 500

# You might also want to add a 404 handler for unknown routes, but we can add that later if needed.
# @app.errorhandler(404)
# def not_found_error(error):
#     return jsonify({"error": "Not Found", "message": "The requested URL was not found on the server."}), 404

if __name__ == '__main__':
    # Run the Flask application
    # debug=True allows for automatic reloading on code changes and provides a debugger.
    # In production, set debug=False.
    app.run(debug=True, port=5000)

    # --- Configuration and Data Loading ---
# Define paths for ingredient data files
# These paths are relative to the directory where app.py is run.
INGREDIENTS_FILE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'common_ingredients_live.json')
STRUCTURED_INGREDIENTS_FILE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'structured_common_ingredients_live.json')
VERIFIED_INGREDIENTS_FILE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'structured_verified_ingredients_reparsed_v2.json')


# Global variables to store loaded data
common_ingredients_set = set()
structured_common_ingredients = []
verified_ingredients_map = {} # New global variable for verified ingredients


def load_json_data(file_path):
    """
    Loads JSON data from a specified file path.
    Returns the loaded data or None if an error occurs.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found at {file_path}")
        return None
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {file_path}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while loading {file_path}: {e}")
        return None


# Load ingredient data on application startup
# It's crucial that these files are in the specified 'data' directory
# relative to your backend folder.
loaded_common_ingredients = load_json_data(INGREDIENTS_FILE_PATH)
if loaded_common_ingredients:
    common_ingredients_set = set(loaded_common_ingredients)
    print(f"Loaded {len(common_ingredients_set)} common ingredients.")
else:
    print("Failed to load common_ingredients_live.json. Application may not function correctly.")

loaded_structured_ingredients = load_json_data(STRUCTURED_INGREDIENTS_FILE_PATH)
if loaded_structured_ingredients:
    structured_common_ingredients = loaded_structured_ingredients
    print(f"Loaded {len(structured_common_ingredients)} structured common ingredients.")
else:
    print("Failed to load structured_common_ingredients_live.json. Application may not function correctly.")

loaded_verified_ingredients = load_json_data(VERIFIED_INGREDIENTS_FILE_PATH)
if loaded_verified_ingredients:
    for ingredient in loaded_verified_ingredients:
        base = ingredient.get('base_ingredient', '').lower()
        mods = tuple(sorted([m.lower() for m in ingredient.get('modifiers', [])]))
        verified_ingredients_map[(base, mods)] = ingredient
    print(f"Loaded {len(verified_ingredients_map)} verified ingredients.")
else:
    print("Failed to load structured_verified_ingredients_reparsed_v2.json. Trust report functionality may not work.")


# --- New Endpoint for Trust Report ---
@app.route('/trust_report', methods=['POST'])
def trust_report():
    """
    Endpoint to provide a trust report for an ingredient string.
    Expects a JSON payload with 'ingredient_string'.
    Parses the ingredient and checks it against a list of verified ingredients.
    """
    if 'parse_ingredient_string' not in globals():
        return jsonify({"error": "Ingredient parser not available. Check server logs."}), 500

    data = request.get_json()
    if not data or 'ingredient_string' not in data:
        return jsonify({"error": "Missing 'ingredient_string' in request body"}), 400

    ingredient_string = data['ingredient_string']
    
    try:
        # Parse the input ingredient string
        parsed_data = parse_ingredient_string(ingredient_string, common_ingredients_set)
        
        report = {
            "original_string": ingredient_string,
            "parsed_data": parsed_data,
            "is_verified": False,
            "verification_details": {},
            "unusual_punctuation_found": parsed_data.get('unusual_punctuation_found', [])
        }

        # Attempt to find the parsed ingredient in the verified map
        base_ingredient = parsed_data.get('base_ingredient', '').lower()
        modifiers = tuple(sorted([m.lower() for m in parsed_data.get('modifiers', [])]))
        lookup_key = (base_ingredient, modifiers)

        if lookup_key in verified_ingredients_map:
            verified_info = verified_ingredients_map[lookup_key]
            report["is_verified"] = True
            report["verification_details"] = {
                "base_ingredient": verified_info.get('base_ingredient'),
                "modifiers": verified_info.get('modifiers'),
                "attributes": verified_info.get('attributes', {}),
                "trust_report_category": verified_info.get('attributes', {}).get('trust_report_category', 'unknown')
            }
        else:
            report["verification_details"] = {
                "message": "Ingredient not found in verified list. Trust report category is 'unknown' by default.",
                "trust_report_category": parsed_data.get('attributes', {}).get('trust_report_category', 'unknown')
            }

        return jsonify(report)

    except Exception as e:
        print(f"Error generating trust report for '{ingredient_string}': {e}")
        return jsonify({"error": f"Failed to generate trust report: {str(e)}"}), 500

