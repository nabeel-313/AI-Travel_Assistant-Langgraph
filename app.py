from ai_travel_planner import langgraph_chatbot

from flask import Flask, render_template, request, jsonify


app = Flask(__name__)


@app.route("/")
def index():
    """
    Renders the main index page.

    :return: The rendered HTML template for the index page.
    """
    return render_template('index.html')


@app.route('/data', methods=['POST'])
def get_data():
    """
    Handles POST requests to process user data and generate a response.

    :return: A JSON response with the generated output.
        - response: Boolean indicating success.
        - message: The output generated from the user's input.
    :raises Exception: If the `generate_response` function encounters an error.
    """
    data = request.get_json()
    text = data.get('data')
    user_input = text
    print(user_input)
    out = langgraph_chatbot(user_input)
    # If output is a dict and includes non-serializable messages, fix it
    if isinstance(out, dict) and "output" in out:
        response_message = out["output"]
    else:
        response_message = str(out)  # Fallback to string
    return jsonify({"response": True, "message": response_message})
    # return jsonify({"response":True,"message":out})


if __name__ == '__main__':
    app.run(debug=True)
