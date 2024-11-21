from openai import AsyncOpenAI
import json
import os
import asyncio
import chainlit as cl
import aiohttp
from dotenv import load_dotenv
import anthropic
from prompt_template import search_strategy_prompt, search_strategy_agent_system_prompt
# Load environment variables from .env file
load_dotenv()

# Retrieve the OpenAI API key from environment variables
api_key = os.getenv("OPENAI_API_KEY")
client = AsyncOpenAI(api_key=api_key)

# Initialize the Anthropic client with API key
anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
if not anthropic_api_key:
    raise ValueError("ANTHROPIC_API_KEY not found in environment variables.")
anthropic_client = anthropic.Anthropic(api_key=anthropic_api_key)

@cl.set_starters
async def set_starters():
    return [
        cl.Starter(
            label="Format PICO",
            message="Can you help me format PICO in a way that I can use it to search PubMed/Medline?",
            icon="/public/pico.png",
        ),
        cl.Starter(
            label="Find synonyms for a word",
            message="Search web for synonyms for a term",
            icon="/public/synonym.png",
        ),
        cl.Starter(
            label="Complete list of key concepts",
            message="Create a list of key concepts for a HEOR research question.",
            icon="/public/concept.png",
        ),
        cl.Starter(
            label="Generate a search strategy",
            message="Generate a search strategy for a HEOR research question.",
            icon="/public/strategy.png",
        ),
    ]

@cl.step(type="tool", show_input="json", language="json")
async def search_tool(query: str, engine: str = "google") -> str:
    """Perform a search query using the SearchAPI and return the cleaned JSON results."""
    search_api_key = os.environ.get("SEARCH_API_KEY")
    if not search_api_key:
        return json.dumps({"error": "SEARCH_API_KEY not found in environment variables."})
    
    url = "https://www.searchapi.io/api/v1/search"
    params = {
        "engine": engine,
        "q": query,
        "api_key": search_api_key
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    return json.dumps({"error": f"Request failed with status code {response.status}."})
                try:
                    data = await response.json()
                except aiohttp.ContentTypeError:
                    return json.dumps({"error": "Failed to parse JSON response."})
        except aiohttp.ClientError as e:
            return json.dumps({"error": f"HTTP request failed: {str(e)}"})
    
    def remove_data_images(obj):
        if isinstance(obj, dict):
            return {k: remove_data_images(v) for k, v in obj.items() 
                   if not (isinstance(v, str) and v.startswith("data:image/"))}
        elif isinstance(obj, list):
            return [remove_data_images(item) for item in obj]
        return obj
    
    if data:
        cleaned_data = remove_data_images(data)
        return json.dumps(cleaned_data, indent=2)
    return json.dumps({"error": "No data returned from the search API."})

@cl.step(type="tool", show_input="json", language="json")
async def pico_tool(query: str) -> str:
    """Generate a PICO framework using Claude from Anthropic.
    
    Args:
        query (str): The clinical question to analyze
        
    Returns:
        str: PICO framework response or error message
    """
    try:
        response = anthropic_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            system="You are a master at forming PICO criteria based on the user's query.",
            messages=[{
                "role": "user", 
                "content": query  # Changed from list to direct string
            }],
            max_tokens=1000,
            temperature=0,
        )
        return response.content[0].text  # Access the response text correctly
    except Exception as e:
        return json.dumps({"error": f"Failed to generate PICO: {str(e)}"})
    
@cl.step(type="tool", show_input="json", language="json")
async def search_strategy_tool(query: str) -> str:
    """Generate a PICO framework using Claude from Anthropic.
    
    Args:
        query (str): The clinical question to analyze
        
    Returns:
        str: PICO framework response or error message
    """
    try:
        response = anthropic_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            system= search_strategy_prompt,
            messages=[{
                "role": "user", 
                "content": query
            }],
            max_tokens=1000,
            temperature=0,
        )
        return response.content[0].text  # Access the response text correctly
    except Exception as e:
        return json.dumps({"error": f"Failed to generate PICO: {str(e)}"})

tools = [
    {
        "type": "function",
        "function": {
            "name": "search_tool",
            "description": "Perform a web search using the specified query and engine.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query string."},
                    "engine": {
                        "type": "string",
                        "enum": ["google"],
                        "description": "The search engine to use."
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pico_tool",
            "description": "Generate a PICO framework using Claude.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The query for PICO framework generation.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_strategy_tool",
            "description": "Generate search strategy using Claude",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The query for search strategy generation.",
                    },
                },
                "required": ["query"],
            },
        },
    }
]


@cl.on_chat_start
def start_chat():
    cl.user_session.set(
        "message_history",
        [{"role": "system", "content": search_strategy_agent_system_prompt}]
    )

@cl.on_message
async def run_conversation(message: cl.Message):
    message_history = cl.user_session.get("message_history")
    message_history.append({"role": "user", "content": message.content})

    # First API call
    response = await client.chat.completions.create(
        model="gpt-4o",  # Fixed model name
        messages=message_history,
        tools=tools,
        tool_choice="auto",
    )
    
    response_message = response.choices[0].message
    
    # Only send the message if it has content
    if response_message.content:
        await cl.Message(author="Assistant", content=response_message.content).send()

    # Process tool calls if any
    if response_message.tool_calls:
        # Add assistant's message to history
        message_history.append(response_message.model_dump())

        # Process tool calls
        for tool_call in response_message.tool_calls:
            try:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                
                # Call the appropriate function
                if function_name == "search_tool":
                    result = await search_tool(
                        query=function_args.get("query"),
                        engine=function_args.get("engine", "google")
                    )
                elif function_name == "pico_tool":
                    result = await pico_tool(query=function_args.get("query"))
                elif function_name == "search_strategy_tool":
                    result = await search_strategy_tool(query=function_args.get("query"))
                else:
                    result = json.dumps({"error": f"Unknown function {function_name}"})

                # Add tool response to message history
                message_history.append({
                    "role": "tool",
                    "content": result,
                    "tool_call_id": tool_call.id,
                    "name": function_name
                })
            except Exception as e:
                print(f"Error processing tool call: {e}")
                message_history.append({
                    "role": "tool",
                    "content": json.dumps({"error": str(e)}),
                    "tool_call_id": tool_call.id,
                    "name": function_name
                })

        # Second API call with tool results
        second_response = await client.chat.completions.create(
            model="gpt-4o",  # Fixed model name
            messages=message_history,
            stream=True
        )
        
        second_message = second_response.choices[0].message
        if second_message.content:
            await cl.Message(author="Assistant", content=second_message.content).send()
            message_history.append(second_message.model_dump())