"""
LLM API Cost Calculator
Author: Prajwal Srinivas
Description: This app fetches pricing data for various LLM providers and calculates
             the total cost based on user inputs (tokens, API calls, etc.). It displays
             the results in both a table and an interactive chart.
"""

# =============================================================================
# Section 1: Imports
# =============================================================================
import json
import re
from typing import Dict, Tuple

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from bs4 import BeautifulSoup

# =============================================================================
# Section 2: Global Constants and Configuration
# =============================================================================
st.set_page_config(page_title="LLM API Cost Calculator", page_icon="💰", layout="wide")

DATA_URL = "https://docsbot.ai/tools/gpt-openai-api-pricing-calculator"
CACHE_TTL = 60 * 60  # 60 minutes caching time for remote data
DEFAULT_PROVIDERS = ["Anthropic", "DeepSeek", "OpenAI"]
DEFAULT_MODEL = "GPT-4o mini"
JSON_FILE_PATH = "cost.json"
EXCHANGE_RATE_URL = "https://api.exchangerate-api.com/v4/latest/USD"

# =============================================================================
# Section 3: Data Fetching and Processing Functions
# =============================================================================


@st.cache_data(ttl=CACHE_TTL)
def get_exchange_rate() -> float:
    """
    Fetch and cache the USD to INR exchange rate.

    Returns:
        float: Exchange rate for converting USD to INR. If the fetch fails, returns a fallback rate.
    """
    try:
        response = requests.get(EXCHANGE_RATE_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data["rates"]["INR"]
    except requests.RequestException as e:
        st.error(f"Error fetching exchange rate: {str(e)}")
        return 83.91  # Fallback exchange rate


def extract_pricing_data(js_content: str) -> Dict:
    """
    Extract pricing data from the given JavaScript content string.

    Args:
        js_content (str): JavaScript content containing the pricing data.

    Returns:
        dict: Parsed JSON pricing data if extraction is successful; otherwise, None.
    """
    pattern = r'\s*=\s*({[\s\S]*?"Embedding models"[\s\S]*?}})'
    match = re.search(pattern, js_content)
    if not match:
        return None

    data_str = match.group(1)
    # Clean up the JavaScript object to make it valid JSON
    data_str = data_str.replace("'", '"')
    data_str = re.sub(r"([{,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:", r'\1"\2":', data_str)
    data_str = re.sub(r",(\s*[}\]])", r"\1", data_str)
    data_str = re.sub(r":\s*\.([0-9]+)", r": 0.\1", data_str)
    data_str = data_str[:-1]  # Remove any trailing characters that break JSON parsing
    try:
        data = json.loads(data_str)
        return data
    except json.JSONDecodeError as e:
        st.error(f"Error parsing JSON: {e}")
        return None


@st.cache_data(ttl=CACHE_TTL)
def fetch_llm_api_cost() -> Dict:
    """
    Fetch and parse LLM API cost data from the remote website.

    Returns:
        dict: Dictionary containing pricing data for Chat/Completion models, or an empty dict if an error occurs.
    """
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "user-agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
    }

    try:
        response = requests.get(DATA_URL, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        script_links = [i.get("src", "") for i in soup.find_all("script")]
        # Find the script that contains the pricing data
        target_links = [
            i for i in script_links if "gpt-openai-api-pricing-calculator" in i
        ]
        if not target_links:
            st.error("Pricing data script not found on the page.")
            return {}
        target_script = f"https://docsbot.ai{target_links[0]}"
        script_response = requests.get(target_script, headers=headers, timeout=10)
        script_response.raise_for_status()
        json_data = extract_pricing_data(script_response.text)
        if json_data is None:
            # st.error("Failed to extract pricing data from the script.")
            with open(JSON_FILE_PATH) as f:
                return json.load(f)["Chat/Completion Models"]
            # return {}
        # Optionally write the JSON data to a local file for debugging
        try:
            with open(JSON_FILE_PATH, "w") as f:
                json.dump(json_data, f, indent=4)
        except Exception as e:
            st.warning(f"Could not write JSON data to file: {e}")
        return json_data.get("Chat/Completion Models", {})
    except requests.RequestException as e:
        st.error(f"Error fetching pricing data: {str(e)}")
        return {}


def load_data() -> pd.DataFrame:
    """
    Load and preprocess the LLM API cost data into a pandas DataFrame.

    Returns:
        pd.DataFrame: DataFrame containing preprocessed API cost data.
    """
    data = fetch_llm_api_cost()
    if not data:
        st.error("No pricing data available.")
        return pd.DataFrame()
    df = pd.DataFrame(data)
    # Normalize provider names for consistency
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
    """
    Calculate the total cost and relative cost for each LLM model.

    The function computes a numeric total cost (in USD) based on the input and output token counts,
    the API call count, and the per‑million token costs. It then formats a display column based on the
    selected currency and computes a relative cost using the provided default model as a baseline.

    Args:
        df (pd.DataFrame): DataFrame containing raw API cost data.
        selected_providers (list): List of provider names to include.
        input_tokens (int): Number of input tokens.
        output_tokens (int): Number of output tokens.
        api_calls (int): Number of API calls.
        default_model (str): Model name used as the baseline for relative cost comparison.
        show_token_costs (bool): Flag to indicate whether to display individual token cost details.
        currency (str): Currency code for display ('INR' or 'USD').
        exchange_rate (float): Conversion rate from USD to INR.

    Returns:
        Tuple[pd.DataFrame, float]:
            - pd.DataFrame: DataFrame with computed cost columns (includes both numeric and display columns).
            - float: Numeric cost for the default model (in USD).
    """
    df = df.copy()

    # Calculate numeric total cost (in USD) for each model
    df["Total_numeric"] = (
        (input_tokens / 1_000_000) * df["input_token_cost_per_million"]
        + (output_tokens / 1_000_000) * df["output_token_cost_per_million"]
    ) * api_calls

    # Determine the default cost based on the selected default model
    default_row = df[df["model_name"] == default_model]
    if default_row.empty:
        st.error(f"Default model '{default_model}' not found in the data.")
        default_cost = 0
    else:
        default_cost = default_row["Total_numeric"].iloc[0]

    # Compute relative cost (avoid division by zero)
    if default_cost:
        df["Relative Cost"] = df["Total_numeric"] / default_cost
    else:
        df["Relative Cost"] = float("nan")
    df["Relative Cost"] = df["Relative Cost"].apply(
        lambda x: f"{x:.2f} * {default_model}" if pd.notnull(x) else "N/A"
    )

    # Filter by selected providers and sort by numeric cost
    df = df[df["provider"].isin(selected_providers)].sort_values(by="Total_numeric")

    # Create a formatted display column for the total cost based on selected currency
    if currency.upper() == "INR":
        df["Total_display"] = df["Total_numeric"] * exchange_rate
        df["Total_display"] = df["Total_display"].apply(lambda x: f"₹{x:.2f}")
    else:
        df["Total_display"] = df["Total_numeric"].apply(lambda x: f"${x:.2f}")

    # Optionally add formatted columns for individual token costs
    if show_token_costs:
        if currency.upper() == "INR":
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
    # Return the full DataFrame (which includes the numeric column for calculations) and the default cost.
    return df, default_cost


def create_total_cost_chart(df: pd.DataFrame, currency: str) -> px.bar:
    """
    Create an interactive horizontal bar chart for total cost by model.

    Uses the numeric total cost column ('Total_numeric') for plotting so that formatting does not interfere with calculations.

    Args:
        df (pd.DataFrame): DataFrame containing API cost data with a 'Total_numeric' column.
        currency (str): Currency code ('INR' or 'USD') used for chart title.

    Returns:
        px.bar: Plotly Express bar chart object.
    """
    fig = px.bar(
        df,
        y="model_name",
        x="Total_numeric",
        color="provider",
        title=f"Total Cost by Model ({currency.upper()})",
        orientation="h",
    )
    fig.update_layout(
        yaxis_title="Model",
        xaxis_title=f"Total Cost ({currency.upper()})",
        height=600,
        yaxis={"categoryorder": "total descending"},
    )
    return fig


# =============================================================================
# Section 4: UI Components and Token Estimation Dialog
# =============================================================================


@st.dialog("Calculate number of tokens in text", width="large")
def estimate_dialog():
    """
    Display a dialog to estimate token counts for sample input and output texts using tiktoken.

    The dialog provides a brief explanation and allows users to estimate token counts.
    """
    st.markdown(
        """
        - Enter sample texts below to calculate token counts using the `tiktoken` module.
        - Encoding used: `o200k_base` (used for gpt-4o and gpt-4o-mini models).
        - Note: Different LLM providers may use different tokenizers; these are estimates.
        """
    )
    sample_input = st.text_area("Example Input Text", height=200)
    sample_output = st.text_area("Example Output Text", height=200)
    if st.button("Estimate Tokens"):
        if not sample_input.strip() or not sample_output.strip():
            st.error("Both input and output text examples are required!")
        else:
            try:
                import tiktoken
            except ImportError:
                st.error(
                    "The tiktoken module is not installed. Please install it to use token estimation."
                )
            else:
                enc = tiktoken.encoding_for_model("gpt-4o")
                input_count = len(enc.encode(sample_input))
                output_count = len(enc.encode(sample_output))
                st.session_state.estimated_input_tokens = input_count
                st.session_state.estimated_output_tokens = output_count
                st.success(
                    f"""
                    Token counts estimated: 
                    - Input Tokens: {input_count}
                    - Output Tokens: {output_count}
                    """
                )
    if (
        "estimated_input_tokens" in st.session_state
        and "estimated_output_tokens" in st.session_state
    ):
        if st.button("Populate these token values"):
            st.session_state.input_tokens_manual = (
                st.session_state.estimated_input_tokens
            )
            st.session_state.output_tokens_manual = (
                st.session_state.estimated_output_tokens
            )
            st.rerun()


# =============================================================================
# Section 5: Main App Function
# =============================================================================


def main():
    """
    Main function to run the LLM API Pricing Calculator app.

    This function sets up the sidebar for user inputs, fetches and processes the data,
    computes the costs, and displays the results in both table and chart formats.
    """
    st.subheader("LLM API Pricing Calculator")

    # Load data and get exchange rate
    df_raw = load_data()
    if df_raw.empty:
        st.error("Unable to display pricing data due to previous errors.")
        return

    exchange_rate = get_exchange_rate()

    # Retrieve unique providers and models
    providers = sorted(df_raw["provider"].unique())
    models = sorted(df_raw["model_name"].unique())

    # Retrieve query parameters for input tokens, output tokens, and API calls
    query_params = st.query_params
    default_input = int(
        query_params.get(
            "input_tokens", st.session_state.get("input_tokens_manual", 10000)
        )
    )
    default_output = int(
        query_params.get(
            "output_tokens", st.session_state.get("output_tokens_manual", 3000)
        )
    )
    default_api_calls = int(query_params.get("api_calls", 100))

    # -----------------------------------------------------------------------------
    # Sidebar: User Input Parameters
    # -----------------------------------------------------------------------------
    with st.sidebar:
        selected_providers = st.multiselect(
            "Select Providers", options=providers, default=DEFAULT_PROVIDERS
        )
        default_model = st.selectbox(
            "Select default model for relative cost comparison",
            options=models,
            index=models.index(DEFAULT_MODEL) if DEFAULT_MODEL in models else 0,
        )

        st.info(
            """
            - Calculate total token count by entering input and output text. 
            - If you already know the tokens count, just enter the values manually below
            """
        )

        # Button to open the token estimation dialog
        if st.button("Calculate Token Count", icon="🧮", use_container_width=True):
            estimate_dialog()

        input_tokens = st.number_input(
            "Input Tokens",
            value=default_input,
            min_value=1,
            help="Enter the number of input tokens.",
        )
        output_tokens = st.number_input(
            "Output Tokens",
            value=default_output,
            min_value=1,
            help="Enter the number of output tokens.",
        )

        api_calls = st.number_input(
            "API Calls",
            value=default_api_calls,
            min_value=1,
            help="Enter the number of API calls.",
        )
        show_token_costs = st.toggle(
            "Show input/output tokens cost in table", value=False
        )
        currency = st.radio("Select Currency", options=["INR", "USD"], horizontal=True)

        # Compute costs using the provided parameters
        df_full, default_cost = calculate_costs(
            df_raw,
            selected_providers,
            input_tokens,
            output_tokens,
            api_calls,
            default_model,
            show_token_costs,
            currency,
            exchange_rate,
        )

        # Display the default model cost in the selected currency
        if currency.upper() == "INR":
            formatted_cost = f"₹{default_cost * exchange_rate:.2f}"
        else:
            formatted_cost = f"${default_cost:.2f}"
        st.success(f"Default model **({default_model})** Cost: **{formatted_cost}**")

    # -----------------------------------------------------------------------------
    # Main Content: Display Table and Chart
    # -----------------------------------------------------------------------------
    if selected_providers:
        # For the table, choose display columns (hiding the internal numeric column)
        if show_token_costs:
            table_columns = [
                "model_name",
                "provider",
                "context",
                "Input Token Cost (per 1M)",
                "Output Token Cost (per 1M)",
                "Total_display",
                "Relative Cost",
            ]
        else:
            table_columns = [
                "model_name",
                "provider",
                "context",
                "Total_display",
                "Relative Cost",
            ]

        table_tab, chart_tab = st.tabs(["Table", "Chart"])
        with table_tab:
            st.dataframe(
                df_full[table_columns],
                use_container_width=True,
                height=500,
                hide_index=True,
            )
        with chart_tab:
            fig_total = create_total_cost_chart(df_full, currency)
            st.plotly_chart(fig_total, use_container_width=True)


if __name__ == "__main__":
    main()
