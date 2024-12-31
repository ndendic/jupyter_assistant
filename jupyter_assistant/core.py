# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/00_core.ipynb.

# %% auto 0
__all__ = ['system_prompt', 'model', 'notebook_agent', 'max_lookback', 'get_current_agent', 'create_cell', 'set_agent',
           'find_current_notebook', 'get_notebook_history', 'create_history_aware_prompt', 'run_with_history', 'prompt']

# %% ../nbs/00_core.ipynb 3
import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models import KnownModelName
from typing import Optional, Union
from functools import wraps

load_dotenv()

# Enable async/await in Jupyter
import nest_asyncio
nest_asyncio.apply()

# %% ../nbs/00_core.ipynb 6
from datetime import date
system_prompt = f"""
You are a helpful assistant that operates in a Jupyter notebook.
Your regular text responses are rendered as cell output.
You can create new cells, edit existing cells, and run code.
You can also use tools to help you with your tasks.
Today's date is {date.today().strftime('%Y-%m-%d')}.
"""

# %% ../nbs/00_core.ipynb 7
from typing import cast
model = cast(KnownModelName, os.getenv('PYDANTIC_AI_MODEL', 'openai:gpt-4o'))
print(f'PydanticAI is using model: {model}')
notebook_agent = Agent(model, system_prompt=system_prompt)

# %% ../nbs/00_core.ipynb 8
_current_agent: Optional[Agent] = None

def get_current_agent() -> Agent:
    """Get the current agent, falling back to default notebook_agent if none set."""
    global _current_agent, notebook_agent
    return _current_agent or notebook_agent


# %% ../nbs/00_core.ipynb 11
from IPython.display import display, Markdown
from typing import Literal

@notebook_agent.tool
def create_cell(ctx: RunContext[str], content: str, cell_type: Literal['code', 'markdown'] = 'code') -> str:
    """Create a new cell in the notebook with the specified content.
    
    Args:
        content: The content to put in the new cell
        cell_type: Type of cell to create ('code' or 'markdown')
    
    Returns:
        A confirmation message
    """
    try:    
        ipython = get_ipython()
    except NameError:
        return "Error: Not running in IPython/Jupyter environment"
    
    # Display the content immediately
    if cell_type == 'code':
        # Set up the next cell with the content
        ipython.set_next_input(content)
    else:
        display(Markdown(content))
    
    return f"Created new {cell_type}  with content: {content}"

# %% ../nbs/00_core.ipynb 13
def set_agent(agent: Agent) -> Agent:
    """Set a custom agent for the notebook.
    
    Args:
        agent: PydanticAI agent instance
        
    Returns:
        Configured agent with required tools
    """
    global _current_agent, notebook_agent
        
    # Always ensure create_cell tool is available
    if 'create_cell' not in agent._function_tools:
        # Copy the tool directly from notebook_agent
        agent._function_tools = notebook_agent._function_tools
    
    _current_agent = agent
    return agent

# %% ../nbs/00_core.ipynb 24
import os
import json
from pathlib import Path
from typing import Optional, Dict, Any

# Cache for notebook data
_notebook_cache: Dict[str, Any] = {}

def find_current_notebook() -> Optional[dict]:
    """Find and cache the current notebook data.
    
    Returns:
        Dict containing notebook data or None if not found
    """
    global _notebook_cache
    
    try:
        ipython = get_ipython()
        if not ipython:
            return None
            
        # Get current cell content to identify the notebook
        current_cell = ipython.get_parent()['content']['code']
        
        # Check if we already found the notebook
        if 'notebook' in _notebook_cache:
            # Verify it's still the correct notebook by checking the current cell
            notebook = _notebook_cache['notebook']
            for cell in notebook['cells']:
                if (cell['cell_type'] == 'code' and 
                    ''.join(cell['source']) == current_cell):
                    return notebook
        
        # If not in cache or cache is invalid, search for the notebook
        current_dir = Path.cwd()
        notebook_files = list(current_dir.glob("*.ipynb"))
        
        for nb_file in notebook_files:
            try:
                with open(nb_file) as f:
                    notebook = json.load(f)
                    for cell in notebook['cells']:
                        if (cell['cell_type'] == 'code' and 
                            ''.join(cell['source']) == current_cell):
                            # Found the notebook, cache it
                            _notebook_cache['notebook'] = notebook
                            _notebook_cache['file'] = nb_file
                            return notebook
            except Exception:
                continue
                
        return None
        
    except Exception as e:
        print(f"Error finding notebook: {e}")
        return None


# %% ../nbs/00_core.ipynb 25
max_lookback = 10

def get_notebook_history(max_cells: int = max_lookback) -> list:
    """Get the content of notebook cells between current and last prompt cell.
    
    Args:
        max_cells: Maximum number of previous cells to include
        
    Returns:
        List of previous cell contents
    """
    try:
        # Get the cached notebook or find it
        notebook = find_current_notebook()
        if not notebook:
            return []
            
        # Find current cell index
        current_cell = get_ipython().get_parent()['content']['code']
        cells = notebook['cells']
        current_idx = -1
        last_prompt_idx = -1
        
        # Find current cell and last prompt cell
        for idx, cell in enumerate(cells):
            source = ''.join(cell['source']) if isinstance(cell['source'], list) else cell['source']
            
            # Find current cell
            if current_idx == -1 and cell['cell_type'] == 'code' and source == current_cell:
                current_idx = idx
                
            # Find last prompt cell before current cell
            if idx < current_idx or current_idx == -1:  # Only look at cells before current
                if cell['cell_type'] == 'code' and source.strip().startswith('%%prompt'):
                    last_prompt_idx = idx
                
        if current_idx == -1:
            return []
            
        # Get cells between last prompt and current cell
        start_idx = last_prompt_idx + 1 if last_prompt_idx != -1 else max(0, current_idx - max_cells)
        history = []
        
        for idx in range(start_idx, current_idx):
            cell = cells[idx]            
            source = cell['source'] if isinstance(cell['source'], str) else ''.join(cell['source'])
            if 'outputs' in cell:
                outputs = cell['outputs'] if isinstance(cell['outputs'], str) else str(cell['outputs'])
            else:
                outputs = 'None'
            if not (source.strip().startswith('%%prompt') or source.strip().startswith('#|exclude') or source.strip().startswith('#| exclude')):
                history.append(f"Cell[{idx}]:\nSource:\n{source}\nOutputs:\n{outputs}")
        
        return history
        
    except Exception as e:
        print(f"Error getting notebook history: {e}")
        return []

# %% ../nbs/00_core.ipynb 29
def create_history_aware_prompt(prompt: str, message_history: list = None, max_history: int = 5) -> tuple:
    """Create a prompt with notebook history context and message history.
    
    Args:
        prompt: The user's prompt
        message_history: Previous conversation messages from results.all_messages()
        max_history: Maximum number of previous cells to include
        
    Returns:
        Tuple of (enhanced prompt, combined message history)
    """
    try:
        ipython = get_ipython()
        if not ipython:
            return prompt, message_history
        
        # Get new cells using our optimized get_notebook_history
        new_cells = get_notebook_history(max_cells=max_history)
        
        if not new_cells and not message_history:
            return prompt, None
            
        # Create message history if none exists
        from pydantic_ai.messages import (
            ModelRequest, ModelResponse, 
            UserPromptPart, TextPart
        )
        
        messages = []
        
        # Add existing message history if provided
        if message_history:
            messages.extend(message_history)
        
        # Only add context message if we have new cells
        if new_cells:
            # Create context message with new cells
            history_content = "\n\n".join(new_cells)

            context_msg = ModelRequest(parts=[
                UserPromptPart(
                    content="Here is the context of new notebook cells that were added:\n" + history_content
                )
            ])
            
            # Create response acknowledging new context
            context_response = ModelResponse(parts=[
                TextPart(
                    content="I understand the new notebook context. How can I help?"
                )
            ])
            
            messages.extend([context_msg, context_response])
                
        return prompt, messages
        
    except Exception as e:
        print(f"Error creating history-aware prompt: {e}")
        return prompt, message_history

# %% ../nbs/00_core.ipynb 33
from typing import Any
def run_with_history(agent: Agent, prompt: str, message_history: list = None, max_history: int = 5) -> Any:
    """Run the agent with notebook and conversation history context.
    
    Args:
        agent: The PydanticAI agent
        prompt: The user's prompt
        message_history: Previous conversation messages
        max_history: Maximum number of previous cells to include
        
    Returns:
        Agent run result
    """
    prompt, combined_history = create_history_aware_prompt(
        prompt, 
        message_history=message_history, 
        max_history=max_history
    )
    return agent.run_sync(prompt, message_history=combined_history)

# %% ../nbs/00_core.ipynb 38
from IPython.core.magic import register_cell_magic

#| export
@register_cell_magic
def prompt(line, cell):
    """Cell magic to create prompt cells that interact with the AI agent."""
    try:
        # Get the last result's message history if it exists
        message_history = None
        if 'last_prompt_result' in get_ipython().user_ns:
            last_result = get_ipython().user_ns['last_prompt_result']
            if hasattr(last_result, 'all_messages'):
                message_history = last_result.all_messages()
        
        # Use get_current_agent() instead of notebook_agent directly
        agent = get_current_agent()
        
        # Run the prompt through our agent with history context
        result = run_with_history(
            agent, 
            cell.strip(), 
            message_history=message_history
        )
        
        # Store the result for next time
        get_ipython().user_ns['last_prompt_result'] = result
        
        return Markdown(result.data)
    except Exception as e:
        return f"Error processing prompt: {str(e)}"
