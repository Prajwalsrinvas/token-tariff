# LLM API Cost Calculator 🤖🧮

A Streamlit app to calculate, compare, and visualize the costs of various LLM APIs. The app includes real-time pricing data, interactive visualization, and advanced features like token estimation and query parameter support.

[LLM API Cost Calculator demo.webm](https://github.com/user-attachments/assets/b7bd21b6-ade2-4d56-b008-203e0724a464)

![image](https://github.com/user-attachments/assets/7921cef2-507e-4521-8647-8ad7b76cd141)

![image](https://github.com/user-attachments/assets/1ebec78f-61ce-4250-865a-00ed96a73b2c)

![image](https://github.com/user-attachments/assets/ae342797-8d7b-48af-bf8f-91568afc3b9d)

---

## Features

- **Real-time Pricing Data:**  
  Fetches up-to-date pricing information from [LiteLLM's GitHub repository](https://github.com/BerriAI/litellm) using direct JSON API calls with intelligent caching to minimize redundant requests. The raw data is saved to a local file (`model_prices_and_context_window.json`) for fallback and debugging.

- **Smart Model Filtering:**  
  Automatically filters out snapshot/dated model versions (e.g., `gpt-4-0613`, `claude-3-5-sonnet-20241022`) to show only the latest model versions, keeping the interface clean and focused on current offerings.

- **Cost Calculation:**  
  Computes the total cost based on input tokens, output tokens, and API calls. Costs are calculated on a per‑million tokens basis and further compared against a default model to provide a relative cost metric.

- **Relative Cost Comparison:**  
  Compares costs of various models using a user-selected default model (e.g., **gpt-4o-mini**) as the baseline.

- **Provider Filtering:**  
  Allows filtering the results by LLM provider, with automatic normalization of provider names (e.g., "openai" is displayed as "OpenAI").

- **Interactive Visualization:**  
  Displays cost data in both a detailed table and an interactive horizontal bar chart built with Plotly.

- **Currency Conversion:**  
  Supports both USD and INR. A live USD-to-INR exchange rate is fetched and applied, with a fallback rate provided if the fetch fails.

- **Token Estimation Dialog:**  
  Provides a dialog (powered by the `tiktoken` module) for estimating token counts from sample input and output texts. Estimated values are stored in session state and automatically populate the token input fields.

- **Detailed Token Cost Breakdown:**  
  Offers an option to display individual input and output token costs in the results table.

- **Query Parameters Support:**  
  Reads URL query parameters (`input_tokens`, `output_tokens`, and `api_calls`) to pre-populate the respective input fields, ensuring a seamless user experience.

- **Caching & Session State:**  
  Utilizes Streamlit's caching for data fetching and exchange rate lookups. The app leverages session state to retain token estimation results between interactions.

---

## Dependencies

- pandas
- plotly
- requests
- streamlit (supports st.cache_data, st.dialog, and session state)
- tiktoken (optional, for token estimation)

---

## Key Functions

- **`fetch_llm_api_cost()`**  
  Fetches and parses pricing data from LiteLLM's GitHub repository using caching. The raw JSON data is written to `model_prices_and_context_window.json` for fallback and debugging.

- **`load_data()`**  
  Loads and preprocesses the fetched pricing data into a pandas DataFrame, including normalization of provider names and filtering of snapshot models.

- **`is_snapshot_model()`**  
  Detects and filters out snapshot/dated model versions using regex patterns for various date formats (YYYY-MM-DD, YYYYMMDD, OpenAI's MMDD format).

- **`calculate_costs()`**  
  Computes the total and relative costs based on user inputs (input tokens, output tokens, and API calls), applies currency conversion, and optionally includes a detailed breakdown of token costs.

- **`create_total_cost_chart()`**  
  Generates an interactive horizontal bar chart visualizing the total cost per model.

- **`estimate_dialog()`**  
  Opens a dialog for estimating token counts using sample texts. Estimated token counts are stored in session state and automatically populate the token input fields.

---

## Main Application Flow

1. **Data Loading & Preprocessing:**  
   - Fetch pricing data from LiteLLM's GitHub repository and the live USD-to-INR exchange rate.
   - Filter for chat models only, exclude fine-tuned models and snapshot versions.
   - Normalize provider names and prepare the data for cost calculations.

2. **User Input Sidebar:**  
   - **Provider and Model Selection:**  
     Choose which LLM providers to include and select a default model for relative cost comparison.
   - **Token and API Call Inputs:**  
     - Manually enter the number of input tokens, output tokens, and API calls.
     - Alternatively, use URL query parameters (`input_tokens`, `output_tokens`, and `api_calls`) to pre-populate these values. (ex: http://localhost:8501/?input_tokens=2000&output_tokens=300&api_calls=10)
   - **Token Estimation:**  
     Click the "Calculate Token Count" button to open the token estimation dialog. The resulting token counts are automatically populated into the input fields.
   - **Display Options:**  
     - Toggle the display of individual token cost breakdowns.
     - Select the display currency (USD or INR).

3. **Cost Calculation & Visualization:**  
   - Calculate total and relative costs based on the provided inputs.
   - Present the results in a detailed table and an interactive bar chart.

4. **Performance & Debugging:**  
   - Leverages caching to optimize data fetching and exchange rate lookups.
   - Writes fetched pricing data to `model_prices_and_context_window.json` for fallback and debugging purposes.

---

## Usage

To run the application locally:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv --python 3.11
source .venv/bin/activate
uv pip install -r requirements.txt
streamlit run app.py
```

Installs uv -> Installs python (if not present) -> creates and activates venv -> installs requirements  
pip can be used for this too, uv is faster!  
`streamlit run` command will launch the app in your browser. You can modify token values, filter providers, use URL query parameters to pre-populate inputs, and interactively view cost comparisons and visualizations.

---

## Data Source

The app fetches pricing data from [LiteLLM's model pricing repository](https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json), which is continuously updated with the latest model pricing information from various providers including OpenAI, Anthropic, Google, Meta, DeepSeek, and others.

The data is automatically filtered to show only:
- Chat/completion models (excluding embeddings, image generation, etc.)
- Latest model versions (excluding snapshot/dated versions)
- Currently available models (excluding fine-tuned models)

This ensures users see only the most relevant and current pricing information for production use.