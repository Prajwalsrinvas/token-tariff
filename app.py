import json
import re
from typing import Dict, Tuple

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title="LLM API Cost Calculator", page_icon="💰", layout="wide")

# Constants
DATA_URL = "https://docsbot.ai/tools/gpt-openai-api-pricing-calculator"
CACHE_TTL = 60 * 60  # 60 minutes
DEFAULT_PROVIDERS = ["Anthropic", "OpenAI"]
DEFAULT_MODEL = "GPT-4o mini"
JSON_FILE_PATH = "cost.json"
EXCHANGE_RATE_URL = "https://api.exchangerate-api.com/v4/latest/USD"


@st.cache_data(ttl=CACHE_TTL)
def get_exchange_rate() -> float:
    """Fetch and cache the USD to INR exchange rate."""
    try:
        response = requests.get(EXCHANGE_RATE_URL)
        response.raise_for_status()
        data = response.json()
        return data["rates"]["INR"]
    except requests.RequestException as e:
        st.error(f"Error fetching exchange rate: {str(e)}")
        return 83.91  # Fallback exchange rate, as on 2024-09-02


def extract_pricing_data(js_content):
    # Look for the specific data structure in the file
    pattern = r'n\s*=\s*({[\s\S]*?"Embedding models"[\s\S]*?}})'
    match = re.search(pattern, js_content)

    if not match:
        return None

    data_str = match.group(1)

    # Clean up the JavaScript object to make it valid JSON
    # Replace single quotes with double quotes
    data_str = data_str.replace("'", '"')
    # Ensure property names are properly quoted
    data_str = re.sub(r"([{,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:", r'\1"\2":', data_str)
    # Remove any trailing commas before closing brackets
    data_str = re.sub(r",(\s*[}\]])", r"\1", data_str)
    data_str = re.sub(r":\s*\.([0-9]+)", r": 0.\1", data_str)
    data_str = data_str[:-1]
    try:
        # Parse the JSON
        data = json.loads(data_str)
        return data
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        return None


@st.cache_data(ttl=CACHE_TTL)
def fetch_llm_api_cost() -> Dict:
    """Fetch and parse LLM API cost data from the website."""
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    }

    try:
        response = requests.get(DATA_URL, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        script_links = [i.get("src", "") for i in soup.find_all("script")]
        target_script = f"https://docsbot.ai{[i for i in script_links if 'gpt-openai-api-pricing-calculator' in i][0]}"
        script_content = requests.get(target_script, headers=headers)
        script_content.raise_for_status()
        json_data = extract_pricing_data(script_content.text)

        with open(JSON_FILE_PATH, "w") as f:
            json.dump(json_data, f, indent=4)

        return json_data["Chat/Completion Models"]
    except requests.RequestException as e:
        st.error(f"Error fetching data: {str(e)}")
        return {}


def load_data() -> pd.DataFrame:
    """Load and preprocess the LLM API cost data."""
    data = fetch_llm_api_cost()
    df = pd.DataFrame(data)
    df["provider"] = df["provider"].replace("OpenAI / Azure", "OpenAI")
    return df


def calculate_costs(
    df: pd.DataFrame,
    selected_providers: list,
    input_tokens: int,
    output_tokens: int,
    api_calls: int,
    default_model: str,
    show_token_costs: bool,
    currency: str,
    exchange_rate: float,
) -> Tuple[pd.DataFrame, float]:
    """Calculate total and relative costs for each model."""
    df["Total"] = (
        (input_tokens / 1_000_000) * df["input_token_cost_per_million"]
        + (output_tokens / 1_000_000) * df["output_token_cost_per_million"]
    ) * api_calls

    default_cost = df[df.model_name == default_model]["Total"].values[0]
    df["Relative Cost"] = df["Total"] / default_cost
    df["Relative Cost"] = df["Relative Cost"].apply(
        lambda x: f"{x:.2f} * {default_model}"
    )

    df = df.sort_values(by="Total")
    df = df[df.provider.isin(selected_providers)]
    if currency == "INR":
        df["Total"] = df["Total"].apply(lambda x: f"₹{x * exchange_rate:.2f}")
    else:
        df["Total"] = df["Total"].apply(lambda x: f"${x:.2f}")

    if show_token_costs:
        if currency == "INR":
            df["Input Token Cost (per 1M)"] = df["input_token_cost_per_million"].apply(
                lambda x: f"₹{x * exchange_rate:.2f}"
            )
            df["Output Token Cost (per 1M)"] = df[
                "output_token_cost_per_million"
            ].apply(lambda x: f"₹{x * exchange_rate:.2f}")
        else:
            df["Input Token Cost (per 1M)"] = df["input_token_cost_per_million"].apply(
                lambda x: f"${x:.2f}"
            )
            df["Output Token Cost (per 1M)"] = df[
                "output_token_cost_per_million"
            ].apply(lambda x: f"${x:.2f}")
        columns = [
            "model_name",
            "provider",
            "context",
            "Input Token Cost (per 1M)",
            "Output Token Cost (per 1M)",
            "Total",
            "Relative Cost",
        ]
    else:
        columns = ["model_name", "provider", "context", "Total", "Relative Cost"]

    return df[columns], default_cost


def create_total_cost_chart(df: pd.DataFrame, currency: str) -> px.bar:
    """Create a horizontal bar chart for total cost by model."""
    df_chart = df.copy()
    df_chart["Total"] = (
        df_chart["Total"].str.replace("$", "").str.replace("₹", "").astype(float)
    )
    fig = px.bar(
        df_chart,
        y="model_name",
        x="Total",
        color="provider",
        title=f"Total Cost by Model ({currency})",
        orientation="h",
    )
    fig.update_layout(
        yaxis_title="Model",
        xaxis_title=f"Total Cost ({currency})",
        height=600,
        yaxis={"categoryorder": "total descending"},
    )
    return fig


def main():
    st.header("LLM API Pricing Calculator")

    df = load_data()
    providers = df.provider.unique()
    models = df.model_name.unique()
    exchange_rate = get_exchange_rate()

    with st.sidebar:
        st.subheader("Input Parameters")
        input_tokens = st.number_input(
            "Input Tokens",
            value=int(st.query_params.get("input_tokens", 1000)),
            min_value=1,
        )
        output_tokens = st.number_input(
            "Output Tokens",
            value=int(st.query_params.get("output_tokens", 1000)),
            min_value=1,
        )
        api_calls = st.number_input(
            "API Calls", value=int(st.query_params.get("api_calls", 100)), min_value=1
        )

        selected_providers = st.multiselect(
            "Select Providers", options=providers, default=DEFAULT_PROVIDERS
        )
        default_model = st.selectbox(
            "Select default model for relative cost comparison",
            options=models,
            index=models.tolist().index(DEFAULT_MODEL),
        )

        show_token_costs = st.toggle("Show input/output tokens cost", value=False)

        currency = st.radio("Select Currency", options=["INR", "USD"], horizontal=True)

    if selected_providers:
        df_costs, default_cost = calculate_costs(
            df,
            selected_providers,
            input_tokens,
            output_tokens,
            api_calls,
            default_model,
            show_token_costs,
            currency,
            exchange_rate,
        )

        st.dataframe(df_costs, use_container_width=True, hide_index=True)

        fig_total = create_total_cost_chart(df_costs, currency)
        st.plotly_chart(fig_total, use_container_width=True)

        # Display the default model cost
        if currency == "INR":
            st.write(
                f"Default model ({default_model}) cost: ₹{default_cost * exchange_rate:.2f}"
            )
        else:
            st.write(f"Default model ({default_model}) cost: ${default_cost:.2f}")


if __name__ == "__main__":
    main()
