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

# =============================================================================
# Section 2: Global Constants and Configuration
# =============================================================================
st.set_page_config(page_title="LLM API Cost Calculator", page_icon="💰", layout="wide")

DATA_URL = "https://raw.githubusercontent.com/BerriAI/litellm/refs/heads/main/model_prices_and_context_window.json"
CACHE_TTL = 60 * 60  # 60 minutes caching time for remote data
DEFAULT_PROVIDERS = ["Anthropic", "DeepSeek", "OpenAI"]
DEFAULT_MODEL = "gpt-4o-mini"
JSON_FILE_PATH = "model_prices_and_context_window.json"
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


def map_provider_name(provider: str) -> str:
    """
    Map provider names from litellm format to display format.

    Args:
        provider (str): Provider name from litellm data

    Returns:
        str: Formatted provider name
    """
    provider_mapping = {
        "openai": "OpenAI",
        "anthropic": "Anthropic",
        "deepseek": "DeepSeek",
        "google": "Google",
        "amazon": "Amazon",
        "cohere": "Cohere",
        "mistral": "Mistral AI",
        "meta": "Meta",
    }
    return provider_mapping.get(provider.lower(), provider.title())


def is_snapshot_model(model_name: str) -> bool:
    """
    Check if a model name represents a snapshot/dated version.

    Args:
        model_name (str): Model name to check

    Returns:
        bool: True if it's a snapshot model, False otherwise
    """
    # Patterns for dated models
    date_patterns = [
        r"\d{4}-\d{2}-\d{2}",  # YYYY-MM-DD
        r"\d{8}",  # YYYYMMDD
        r"\d{4}\d{2}\d{2}",  # YYYYMMDD (alternate)
        r"-\d{4}-\d{1,2}-\d{1,2}",  # -YYYY-M-D or -YYYY-MM-DD
        r"-\d{4}(?:-|$)",  # OpenAI MMDD format: -MMDD at end or -MMDD- in middle
    ]

    # Check if model name contains any date pattern
    for pattern in date_patterns:
        if re.search(pattern, model_name):
            # Additional validation for OpenAI MMDD format
            if pattern == r"-\d{4}(?:-|$)":
                match = re.search(r"-(\d{4})(?:-|$)", model_name)
                if match:
                    mmdd = match.group(1)
                    month = int(mmdd[:2])
                    day = int(mmdd[2:])
                    # Validate month (01-12) and day (01-31)
                    if 1 <= month <= 12 and 1 <= day <= 31:
                        return True
            else:
                return True

    return False


def format_context(model_data: Dict) -> str:
    """
    Format context information from model data.

    Args:
        model_data (Dict): Model data dictionary

    Returns:
        str: Formatted context string
    """
    max_input = model_data.get("max_input_tokens")
    max_output = model_data.get("max_output_tokens")

    # Format large numbers with K/M suffix
    def format_number(num):
        if num >= 1000000:
            return f"{num/1000000:.0f}M"
        elif num >= 1000:
            return f"{num/1000:.0f}K"
        else:
            return str(num)

    if max_input and max_output:
        return f"{format_number(max_input)}/{format_number(max_output)}"
    elif max_input:
        return f"{format_number(max_input)}"
    elif max_output:
        return f"{format_number(max_output)}"
    else:
        return "N/A"


@st.cache_data(ttl=CACHE_TTL)
def fetch_llm_api_cost() -> Dict:
    """
    Fetch and parse LLM API cost data from LiteLLM GitHub repository.

    Returns:
        dict: Dictionary containing pricing data for Chat/Completion models, or an empty dict if an error occurs.
    """
    try:
        response = requests.get(DATA_URL, timeout=30)
        response.raise_for_status()
        data = response.json()

        # Save to local file for fallback
        try:
            with open(JSON_FILE_PATH, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            st.warning(f"Could not write JSON data to file: {e}")

        return data
    except requests.RequestException as e:
        st.error(f"Error fetching pricing data: {str(e)}")
        # Try to load from local file as fallback
        try:
            with open(JSON_FILE_PATH, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            st.error("No local fallback data available.")
            return {}


def load_data() -> pd.DataFrame:
    """
    Load and preprocess the LLM API cost data into a pandas DataFrame.

    Returns:
        pd.DataFrame: DataFrame containing preprocessed API cost data.
    """
    raw_data = fetch_llm_api_cost()
    if not raw_data:
        st.error("No pricing data available.")
        return pd.DataFrame()

    # Process the data
    processed_models = []

    for model_key, model_data in raw_data.items():
        # Filter for chat models only
        if model_data.get("mode") != "chat":
            continue

        # Skip fine-tuned models
        if model_key.startswith("ft:"):
            continue

        # Skip snapshot/dated models
        if is_snapshot_model(model_key):
            continue

        # Extract required fields
        input_cost_per_token = model_data.get("input_cost_per_token", 0)
        output_cost_per_token = model_data.get("output_cost_per_token", 0)
        provider = model_data.get("litellm_provider", "unknown")

        # Convert to per-million costs
        input_cost_per_million = input_cost_per_token * 1_000_000
        output_cost_per_million = output_cost_per_token * 1_000_000

        processed_model = {
            "model_name": model_key,
            "provider": map_provider_name(provider),
            "context": format_context(model_data),
            "input_token_cost_per_million": input_cost_per_million,
            "output_token_cost_per_million": output_cost_per_million,
        }

        processed_models.append(processed_model)

    # Create DataFrame
    df = pd.DataFrame(processed_models)

    # Sort by provider and model name for consistent display
    df = df.sort_values(["provider", "model_name"])

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

    # Filter default providers to only include those available in the data
    available_default_providers = [p for p in DEFAULT_PROVIDERS if p in providers]
    if not available_default_providers:
        available_default_providers = providers[:3]  # Fallback to first 3 providers

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
            "Select Providers", options=providers, default=available_default_providers
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
