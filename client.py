"""
Client utilities for accessing the Ollama and Regression API services
"""

import requests
import json
import traceback
from config import OLLAMA_API_HOST, REGRESSION_API_HOST, REGRESSION_PREDICT_ENDPOINT

def test_regression_service():
    """
    Test regression service connectivity and provide detailed diagnostics
    
    Returns:
        Dictionary with test results and diagnostics
    """
    results = {
        "service_url": REGRESSION_API_HOST,
        "endpoint": REGRESSION_PREDICT_ENDPOINT,
        "full_url": f"{REGRESSION_API_HOST}{REGRESSION_PREDICT_ENDPOINT}",
        "tests": []
    }
    
    # Test 1: Basic connection to host
    try:
        response = requests.get(REGRESSION_API_HOST, timeout=5)
        results["tests"].append({
            "name": "Basic connection to host",
            "success": True,
            "status_code": response.status_code,
            "response_size": len(response.text) if hasattr(response, "text") else "unknown"
        })
    except Exception as e:
        results["tests"].append({
            "name": "Basic connection to host",
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        })
    
    # Test 2: Connection to predict endpoint
    test_data = {"age": 30, "sex": "male", "bmi": 25.0, "children": 1, "smoker": "no", "region": "northeast"}
    try:
        response = requests.post(
            f"{REGRESSION_API_HOST}{REGRESSION_PREDICT_ENDPOINT}",
            json=test_data,
            timeout=5
        )
        results["tests"].append({
            "name": "Predict endpoint test",
            "success": response.status_code == 200,
            "status_code": response.status_code,
            "response": response.text[:500]  # Truncate if too long
        })
    except Exception as e:
        results["tests"].append({
            "name": "Predict endpoint test",
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        })
    
    # Overall status
    results["overall_success"] = all(test["success"] for test in results["tests"])
    return results

def check_regression_service():
    """
    Check if the regression service is running
    
    Returns:
        Boolean indicating if service is accessible
    """
    try:
        # Most ML APIs might not support HEAD requests, try using GET or a more specific endpoint
        # First try the predict endpoint with a minimal request to see if it's alive
        try:
            # Try a small probe request - not all APIs support GET on the root
            response = requests.get(
                f"{REGRESSION_API_HOST}{REGRESSION_PREDICT_ENDPOINT}", 
                timeout=3
            )
            return True
        except:
            # If that fails, try the root URL
            try:
                response = requests.get(
                    f"{REGRESSION_API_HOST}", 
                    timeout=3
                )
                return True
            except:
                # If all connection attempts fail, service is likely down
                return False
    except:
        return False

def get_regression_prediction(data):
    """
    Get a prediction from the regression model API
    
    Args:
        data: Dictionary with regression model input features
        
    Returns:
        Dictionary with prediction results or error
    """
    # First check if regression service is reachable
    if not check_regression_service():
        return {
            "success": False,
            "error": f"Regression service not running at {REGRESSION_API_HOST}. Please start the service on port 5001."
        }
    
    try:
        response = requests.post(
            f"{REGRESSION_API_HOST}{REGRESSION_PREDICT_ENDPOINT}",
            json=data
        )
        
        if response.status_code == 200:
            return {
                "success": True,
                "prediction": response.json()
            }
        else:
            return {
                "success": False,
                "error": f"API Error: {response.status_code}",
                "details": response.text
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"Request Error: {str(e)}"
        }
        
def process_regression_request_from_prompt(user_message, model="mistral:7b"):
    """
    Process a user prompt to extract regression input data and get a prediction
    
    This function:
    1. Asks the LLM to extract structured data from the user message
    2. Sends that data to the regression model
    3. Returns the prediction with an explanation
    
    Args:
        user_message: String with user's natural language request
        model: LLM model to use for extraction
        
    Returns:
        Dictionary with the regression result and explanation
    """
    # Define system prompt for extraction
    system_prompt = """
    Sen metin içerisindeki sağlık sigortası risk değerlendirmesi için gerekli bilgileri çıkararak JSON formatında düzenleyen bir asistansın. 

    Kullanıcı, yaş, cinsiyet, BMI (vücut kitle indeksi), çocuk sayısı, sigara kullanımı ve bölge bilgilerini içeren bir metin gönderecek. Senin görevin, bu bilgileri aşağıdaki formatta JSON'a dönüştürmektir:

    {
      "input": {
        "age": [yaş değeri, tam sayı],
        "sex": ["male" veya "female"],
        "bmi": [BMI değeri, ondalık sayı],
        "children": [çocuk sayısı, tam sayı],
        "smoker": ["yes" veya "no"],
        "region": ["northeast", "northwest", "southeast" veya "southwest"]
      }
    }

    Eğer bir değer belirtilmemişse, ilgili alanı JSON'dan çıkar. Yalnızca açıkça belirtilen değerleri dahil et.

    Eğer "sigara içmiyor", "sigara kullanmıyor" gibi ifadeler geçiyorsa "smoker": "no" olarak işaretle.
    Eğer "sigara içiyor", "sigara kullanıyor" gibi ifadeler geçiyorsa "smoker": "yes" olarak işaretle.

    Cinsiyet için "erkek", "bay", "adam" gibi ifadeler "male" olarak, "kadın", "bayan", "hanım" gibi ifadeler "female" olarak işaretlenmelidir.

    Bölge bilgileri için:
    - "kuzeydoğu", "kuzey doğu" ifadeleri "northeast"
    - "kuzeybatı", "kuzey batı" ifadeleri "northwest"
    - "güneydoğu", "güney doğu" ifadeleri "southeast"
    - "güneybatı", "güney batı" ifadeleri "southwest"

    olarak işaretlenmelidir.

    Sadece JSON çıktısını döndür, başka açıklama ekleme.
    """
    
    # Ask LLM to extract structured data
    try:
        extraction_response = requests.post(
            f"{OLLAMA_API_HOST}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ]
            }
        )
        
        if extraction_response.status_code != 200:
            return {
                "success": False,
                "error": f"LLM API Error: {extraction_response.status_code}"
            }
        
        # Get the extracted JSON from the LLM response
        try:
            # Initialize llm_content as empty in case of early error
            llm_content = ""
            response_json = extraction_response.json()
            # Check Ollama API response format (might be different based on version)
            if "message" in response_json and "content" in response_json["message"]:
                llm_content = response_json["message"]["content"]
            elif "response" in response_json:
                # Alternative format in some Ollama versions
                llm_content = response_json["response"]
            else:
                # Debug output to see what format we're actually getting
                return {
                    "success": False,
                    "error": f"Unexpected LLM API response format",
                    "response_structure": str(response_json.keys())
                }
            
            # Try to find and extract JSON from the text (LLM might add explanations)
            import re
            json_match = re.search(r'\{.*\}', llm_content, re.DOTALL)
            if json_match:
                llm_content = json_match.group(0)
                
            # Parse the JSON data
            parsed_data = json.loads(llm_content)
            
            # Extract the input data from the new JSON structure
            if "input" in parsed_data:
                regression_data = parsed_data["input"]
            else:
                regression_data = parsed_data  # Fallback to old format if needed
            
            # Make prediction with regression model
            prediction_result = get_regression_prediction(regression_data)
            
            if prediction_result["success"]:
                # Format nice explanation
                prediction_data = prediction_result["prediction"]
                # Format input data for display
                age = regression_data.get('age', 'N/A')
                sex = regression_data.get('sex', 'N/A')
                bmi = regression_data.get('bmi', 'N/A')
                children = regression_data.get('children', 'N/A')
                smoker = regression_data.get('smoker', 'N/A')
                region = regression_data.get('region', 'N/A')
                
                explanation = {
                    "success": True,
                    "input_data": regression_data,
                    "prediction_result": prediction_data,
                    "explanation": f"Based on the input features (age: {age}, sex: {sex}, BMI: {bmi}, children: {children}, smoker: {smoker}, region: {region}), the regression model predicts: {prediction_data}"
                }
                return explanation
            else:
                return prediction_result
                
        except json.JSONDecodeError:
            return {
                "success": False,
                "error": "Failed to parse LLM output as JSON",
                "llm_output": llm_content,
                "prompt": system_prompt[:100] + "..."  # Include part of the prompt for debugging
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Processing error: {str(e)}",
                "traceback": traceback.format_exc()
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"LLM request error: {str(e)}",
            "traceback": traceback.format_exc(),
            "prompt": system_prompt[:100] + "..."
        }

def check_lights_service():
    """
    Check if the home lights control service is running
    
    Returns:
        Boolean indicating if service is accessible
    """
    try:
        from config import LIGHTS_API_HOST, LIGHTS_API_ENDPOINT
        print(f"[DEBUG] Işık servisi kontrol ediliyor (host: {LIGHTS_API_HOST})")
        
        # Try to make a simple API request first (more reliable than socket check)
        try:
            import requests
            response = requests.get(f"{LIGHTS_API_HOST}{LIGHTS_API_ENDPOINT}", timeout=1)
            if response.status_code == 200:
                print(f"[DEBUG] Işık servisi API yanıt verdi: {response.status_code}")
                return True
        except:
            # If API request fails, fall back to socket check
            pass
            
        # Parse the host for socket check (extract hostname/IP and port)
        import urllib.parse
        parsed_url = urllib.parse.urlparse(LIGHTS_API_HOST)
        hostname = parsed_url.hostname or 'localhost'
        port = parsed_url.port or 5004
        
        # Simply check if we can connect to the port
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex((hostname, port))
        sock.close()
        
        is_running = result == 0
        print(f"[DEBUG] Işık servisi çalışıyor mu? (Socket kontrolü: {is_running})")
        return is_running
    except Exception as e:
        print(f"[ERROR] Işık servisi kontrolünde hata: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def control_home_lights(room, turn_on=True):
    """
    Control the lights in a specified room of the home
    
    Args:
        room: String name of the room (e.g., "living_room", "bedroom", "toilet", etc.)
        turn_on: Boolean indicating whether to turn lights on (True) or off (False)
        
    Returns:
        Dictionary with the result of the operation
    """
    from config import LIGHTS_API_HOST, LIGHTS_API_ENDPOINT
    
    print(f"[DEBUG] Işık kontrolü çağrıldı: Oda={room}, Durum={turn_on}")
    
    try:
        import requests
        # API zaten çalışıyor, direkt olarak istek gönderelim
        api_url = f"{LIGHTS_API_HOST}{LIGHTS_API_ENDPOINT}"
        api_data = {"room": room, "lights": turn_on}
        
        print(f"[DEBUG] Işık API'sine istek yapılıyor: URL={api_url}, Data={api_data}")
        
        # Timeout değerini düşürerek yanıt süresini hızlandıralım
        response = requests.post(
            api_url,
            json=api_data,
            timeout=2.0  # 2 saniye timeout ekleyelim
        )
        
        if response.status_code == 200:
            action = "açıldı" if turn_on else "kapatıldı"
            print(f"[SUCCESS] {room.capitalize()} odası ışıkları {action}.")
            return {
                "success": True,
                "message": f"{room.capitalize()} odası ışıkları {action}.",
                "room": room,
                "status": "on" if turn_on else "off"
            }
        else:
            print(f"[ERROR] API yanıt kodu: {response.status_code}, Detay: {response.text}")
            return {
                "success": False,
                "error": f"API Hatası: {response.status_code}",
                "details": response.text
            }
            
    except requests.exceptions.Timeout:
        print(f"[ERROR] API isteği zaman aşımına uğradı: {api_url}")
        return {
            "success": False,
            "error": "API yanıt vermedi, zaman aşımı oluştu. Servis çalışıyor ancak yanıt vermiyor.",
            "room": room,
            "status": "unknown"
        }
    except requests.exceptions.ConnectionError:
        print(f"[ERROR] API bağlantı hatası: {api_url}")
        return {
            "success": False,
            "error": "API bağlantı hatası. Işık kontrol servisi çalışmıyor olabilir.",
            "room": room,
            "status": "unknown"
        }
    except Exception as e:
        print(f"[ERROR] Işık kontrolünde beklenmeyen hata: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": f"Beklenmeyen hata: {str(e)}",
            "room": room,
            "status": "unknown"
        }
    except requests.exceptions.ConnectionError:
        print(f"[ERROR] API'ye bağlantı kurulamadı: {api_url}")
        return {
            "success": False,
            "error": "API'ye bağlantı kurulamadı. Servis çalıştığından emin olun."
        }
    except Exception as e:
        import traceback
        print(f"[ERROR] Beklenmeyen hata: {str(e)}")
        traceback.print_exc()
        return {
            "success": False,
            "error": f"İstek Hatası: {str(e)}",
            "traceback": traceback.format_exc()
        }

def process_lights_command_from_text(user_message, model="mistral:7b"):
    """
    Process a natural language command to control home lights
    
    This function:
    1. Asks the LLM to extract room and action (turn on/off) from user message
    2. Sends a command to the lights API
    3. Returns the result
    
    Args:
        user_message: String with user's natural language command
        model: LLM model to use for extraction
        
    Returns:
        Dictionary with the lights control result
    """
    # Define system prompt for extraction
    system_prompt = """
    You are a language model assistant used for home automation.

    The user will give you natural language instructions to turn the home lights on or off.
    Your task is to understand which room's lights should be controlled and provide output in JSON format.

    You must understand commands in both Turkish and English.

    The following rooms are supported for light control:
    - living_room (salon, oturma odası, misafir odası, lounge, etc.)
    - sitting_room (sitting room, oturulan, sitting area)
    - kitchen (mutfak)
    - bedroom (yatak odası, uyku odası)
    - bathroom (banyo, duş, shower)
    - toilet (tuvalet, wc, lavabo, etc.)

    The output you provide should be in the following format:
    {
      "room": "room_name",
      "lights": true/false (true to turn on, false to turn off)
    }

    Examples:
    - "Turn on the living room lights" -> {"room": "living_room", "lights": true}
    - "Turn off the kitchen lights" -> {"room": "kitchen", "lights": false}
    - "Switch off the bedroom lamp" -> {"room": "bedroom", "lights": false}
    - "Salonun ışıklarını aç" -> {"room": "living_room", "lights": true}
    - "Mutfaktaki ışıkları kapat" -> {"room": "kitchen", "lights": false}
    - "Yatak odasındaki lambayı söndür" -> {"room": "bedroom", "lights": false}

    If the user message does not specify a room or specifies a room that is not supported, default to "living_room."

    If the instruction to turn on or off is not specified, default to turning the lights on (lights: true).

    Only return the JSON output, do not include any additional explanation.
    """
    
    # Try to determine room and action directly from keywords
    def extract_from_keywords(text):
        text = text.lower()
        room = "living_room"  # Default room
        turn_on = True  # Default action
        
        # Room keywords
        if any(kw in text for kw in ["salon", "living room", "oturma", "misafir", "lounge"]):
            room = "living_room"
        elif any(kw in text for kw in ["sitting", "sitting room", "oturulan", "sitting area"]):
            room = "sitting_room"    
        elif any(kw in text for kw in ["mutfak", "kitchen"]):
            room = "kitchen"
        elif any(kw in text for kw in ["yatak", "bedroom", "uyku", "sleep"]):
            room = "bedroom"
        elif any(kw in text for kw in ["banyo", "bathroom", "duş", "shower"]):
            room = "bathroom"
        elif any(kw in text for kw in ["tuvalet", "toilet", "wc", "lavabo"]):
            room = "toilet"
        
        # Action keywords
        if any(kw in text for kw in ["kapat", "söndür", "turn off", "switch off", "off"]):
            turn_on = False
        
        return room, turn_on
    
    # Ask LLM to extract structured data
    try:
        import requests
        import json
        import re
        import traceback
        from config import OLLAMA_API_HOST
        
        print(f"[DEBUG] Processing lights command: '{user_message}' with model '{model}'")
        
        # First extract info using keyword matching as fallback
        fallback_room, fallback_turn_on = extract_from_keywords(user_message)
        print(f"[DEBUG] Fallback extraction: room='{fallback_room}', action={fallback_turn_on}")
        
        extraction_response = requests.post(
            f"{OLLAMA_API_HOST}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ]
            }
        )
        
        if extraction_response.status_code != 200:
            print(f"[ERROR] LLM API error: {extraction_response.status_code}")
            # Use fallback if LLM API fails
            print(f"[INFO] Using fallback values: room='{fallback_room}', action={fallback_turn_on}")
            return control_home_lights(fallback_room, fallback_turn_on)
        
        # Get the extracted JSON from the LLM response
        try:
            # Initialize llm_content as empty in case of early error
            llm_content = ""
            
            try:
                response_json = extraction_response.json()
                print(f"[DEBUG] Response JSON keys: {list(response_json.keys())}")
                
                # Check Ollama API response format
                if "message" in response_json and "content" in response_json["message"]:
                    llm_content = response_json["message"]["content"]
                    print(f"[DEBUG] Found content in message.content: {llm_content[:50]}...")
                elif "response" in response_json:
                    # Alternative format in some Ollama versions
                    llm_content = response_json["response"]
                    print(f"[DEBUG] Found content in response: {llm_content[:50]}...")
                else:
                    print(f"[WARNING] Unexpected API format with keys: {list(response_json.keys())}")
                    # Use fallback values
                    print(f"[INFO] Using fallback values: room='{fallback_room}', action={fallback_turn_on}")
                    return control_home_lights(fallback_room, fallback_turn_on)
            except json.JSONDecodeError as je:
                print(f"[ERROR] Response not valid JSON: {str(je)}")
                print(f"[DEBUG] Raw response: {extraction_response.text[:200]}")
                # Use fallback values
                print(f"[INFO] Using fallback values: room='{fallback_room}', action={fallback_turn_on}")
                return control_home_lights(fallback_room, fallback_turn_on)
            
            # Check if llm_content is empty or too short
            if not llm_content or len(llm_content.strip()) < 2:
                print("[WARNING] LLM returned empty or too short content")
                # Use fallback values
                print(f"[INFO] Using fallback values: room='{fallback_room}', action={fallback_turn_on}")
                return control_home_lights(fallback_room, fallback_turn_on)
                
            # Try to find and extract JSON from the text
            json_match = re.search(r'\{.*\}', llm_content, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                print(f"[DEBUG] Extracted JSON: {json_str}")
                try:
                    # Parse the JSON data
                    parsed_data = json.loads(json_str)
                    # Extract the room and action
                    room = parsed_data.get("room", fallback_room)
                    turn_on = parsed_data.get("lights", fallback_turn_on)
                    
                    print(f"[DEBUG] Successfully extracted: room='{room}', action={turn_on}")
                    
                    # Control the lights
                    result = control_home_lights(room, turn_on)
                    return result
                except json.JSONDecodeError:
                    print(f"[ERROR] Extracted pattern is not valid JSON: {json_str}")
                    # Use fallback values
                    print(f"[INFO] Using fallback values: room='{fallback_room}', action={fallback_turn_on}")
                    return control_home_lights(fallback_room, fallback_turn_on)
            else:
                print(f"[WARNING] No JSON pattern found in: {llm_content}")
                # Use fallback values
                print(f"[INFO] Using fallback values: room='{fallback_room}', action={fallback_turn_on}")
                return control_home_lights(fallback_room, fallback_turn_on)
                
        except json.JSONDecodeError:
            print(f"[ERROR] JSON decode error for content: '{llm_content}'")
            # Use fallback values
            print(f"[INFO] Using fallback values: room='{fallback_room}', action={fallback_turn_on}")
            return control_home_lights(fallback_room, fallback_turn_on)
        except Exception as e:
            print(f"[ERROR] Processing error: {str(e)}")
            traceback.print_exc()
            # Use fallback values
            print(f"[INFO] Using fallback values: room='{fallback_room}', action={fallback_turn_on}")
            return control_home_lights(fallback_room, fallback_turn_on)
            
    except Exception as e:
        print(f"[ERROR] LLM request error: {str(e)}")
        traceback.print_exc()
        
        # Extract directly from keywords as fallback
        room, turn_on = extract_from_keywords(user_message)
        print(f"[INFO] Using fallback extraction: room='{room}', action={turn_on}")
        return control_home_lights(room, turn_on)

def get_home_lights_states():
    """
    Get the current state of all room lights
    
    Returns:
        Dictionary with the states of all room lights
    """
    from config import LIGHTS_API_HOST
    
    try:
        import requests
        
        # Make a GET request to the API
        api_url = f"{LIGHTS_API_HOST}/api/get_states"
        
        response = requests.get(api_url, timeout=2.0)
        
        if response.status_code == 200:
            return {
                "success": True,
                "states": response.json()
            }
        else:
            return {
                "success": False,
                "error": f"API Error: {response.status_code}",
                "details": response.text
            }
            
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": "API request timed out"
        }
    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "error": "Could not connect to API. Light control service may not be running."
        }
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "traceback": traceback.format_exc()
        }

def process_lights_status_query_from_text(user_message, model="mistral:7b"):
    """
    Process a natural language query about home light status
    
    This function:
    1. Checks if the query is about listing rooms or getting light states
    2. Gets the current light states from the API
    3. Uses an LLM to format a natural language response
    
    Args:
        user_message: String with user's natural language query
        model: LLM model to use for response generation
        
    Returns:
        Dictionary with the query result and formatted response
    """
    import json
    
    # Get current light states
    states_result = get_home_lights_states()
    
    if not states_result["success"]:
        return {
            "success": False,
            "error": states_result["error"]
        }
        
    room_states = states_result["states"]
    
    # Define system prompt for LLM
    system_prompt = f"""
    You are a language model assistant used for home automation.
    
    The user will ask questions about the status of home lights or which rooms are available.
    You should provide a helpful response based on the current state of the lights.
    
    Here is the current status of all rooms:
    {json.dumps(room_states, indent=2)}
    
    When responding to queries:
    1. If the user asks about specific room(s), tell them whether the lights are on or off in those rooms.
    2. If the user asks to list all rooms, provide the names of all available rooms.
    3. If the user asks about the status of all rooms, list each room and whether its lights are on or off.
    
    Your responses should be conversational and helpful. Respond in the same language the user used for their query (English or Turkish).
    """
    
    try:
        import requests
        from config import OLLAMA_API_HOST
        
        # Ask LLM to generate a response
        response = requests.post(
            f"{OLLAMA_API_HOST}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ]
            }
        )
        
        if response.status_code != 200:
            return {
                "success": False,
                "error": f"LLM API Error: {response.status_code}"
            }
            
        # Parse the response
        response_json = response.json()
        
        if "message" in response_json and "content" in response_json["message"]:
            content = response_json["message"]["content"]
        elif "response" in response_json:
            content = response_json["response"]
        else:
            return {
                "success": False,
                "error": "Unexpected LLM API response format"
            }
            
        return {
            "success": True,
            "message": content,
            "states": room_states
        }
        
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": f"Error processing query: {str(e)}",
            "traceback": traceback.format_exc()
        }