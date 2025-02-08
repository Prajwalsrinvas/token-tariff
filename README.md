# LLM API Cost Calculator

Streamlit app to calculate and compare the costs of various LLM APIs based on input parameters.

[streamlit-app-2025-02-08-10-02-97.webm](https://github.com/user-attachments/assets/785cf94f-6b8a-4f11-8a77-ae285ff46c5f)


![image](https://github.com/user-attachments/assets/da5e6e0f-8ef9-4a0b-ab23-2e90731eca05)

![image](https://github.com/user-attachments/assets/ee8f633e-1bdb-40fb-83f7-4eeed4454bd2)



## Features

- Fetches up-to-date pricing data from [docsbot.ai](https://docsbot.ai/tools/gpt-openai-api-pricing-calculator)
- Allows user input for tokens and API calls
- Filters results by provider
- Calculates total and relative costs
- Visualizes costs with an interactive bar chart

## Dependencies

- pandas
- plotly
- requests
- beautifulsoup4
- streamlit

## Key Functions

### `fetch_llm_api_cost()`

Fetches and parses LLM API cost data from the website. Uses caching to reduce API calls.

### `load_data()`

Loads and preprocesses the LLM API cost data into a pandas DataFrame.

### `calculate_costs()`

Calculates total and relative costs for each model based on user inputs.

### `create_total_cost_chart()`

Creates a horizontal bar chart visualizing total costs by model.

## Main Application Flow

1. Load and preprocess data
2. Display user input sidebar for parameters and filtering
3. Calculate costs based on user inputs
4. Display results in a table and chart

## Usage

Run the application with:

```
streamlit run app.py
```
