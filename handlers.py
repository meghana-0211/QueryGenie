from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from config import logger
from genai_client import generate_content
from utils import structure_message
from weather import get_weather
import re

# Initialize chat histories with a limit to prevent memory bloat
CHAT_HISTORY_LIMIT = 10
chat_histories = {}
ROLE_SYSTEM = "system"
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"

class MessageFormatter:
    @staticmethod
    def escape_markdown_v2(text: str) -> str:
        """Escapes special characters for Telegram's MarkdownV2 format."""
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        escaped_text = text
        for char in special_chars:
            escaped_text = escaped_text.replace(char, f'\\{char}')
        return escaped_text

    @staticmethod
    def format_response(text: str) -> str:
        """Formats the response with proper Markdown escaping while preserving formatting."""
        # First escape all special characters
        escaped_text = MessageFormatter.escape_markdown_v2(text)
        
        # Then restore intended formatting patterns
        # Fix bold patterns
        escaped_text = re.sub(r'\\\*\\\*(.*?)\\\*\\\*', r'*\1*', escaped_text)
        # Fix italic patterns
        escaped_text = re.sub(r'\\\_(.*?)\\_', r'_\1_', escaped_text)
        # Fix code patterns
        escaped_text = re.sub(r'\\\`(.*?)\\\`', r'`\1`', escaped_text)
        
        return escaped_text

def initialize_chat_history(user_id: int):
    """Initialize or reset chat history for a user."""
    chat_histories[user_id] = [
        structure_message(ROLE_SYSTEM, "You are QueryGenie, a Telegram bot integrated with the Gemini API to assist users on Telegram (developed by Vineet Kumar)."),
        structure_message(ROLE_SYSTEM, "I'm QueryGenie, ready to assist! Ask me anything."),
    ]

def trim_chat_history(user_id: int):
    """Ensure chat history does not exceed the limit."""
    if len(chat_histories[user_id]) > CHAT_HISTORY_LIMIT:
        chat_histories[user_id] = chat_histories[user_id][-CHAT_HISTORY_LIMIT:]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    user_id = update.effective_user.id
    initialize_chat_history(user_id)
    welcome_message = "Hello\\! I'm *QueryGenie*\\. How can I assist you today?"
    await update.message.reply_text(
        welcome_message,
        parse_mode=ParseMode.MARKDOWN_V2
    )
    logger.info(f"Initialized chat history for user ({user_id})")

async def weather(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /weather command."""
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text(
            "Please provide a city name\\. Usage: `/weather <city>`",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    
    city = ' '.join(context.args)
    
    try:
        weather_info = get_weather(city)
        logger.info(f"User ({user_id}) requested weather for {city}")
        
        # Format weather info with Markdown
        formatted_weather = MessageFormatter.format_response(
            f"Weather in *{city}*:\n{weather_info}"
        )
        
        await update.message.reply_text(
            formatted_weather,
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except Exception as e:
        logger.error(f"Error fetching weather for {city}: {str(e)}")
        await update.message.reply_text(
            "Sorry, I couldn't fetch the weather\\. Please try again later\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the chatbot conversation."""
    user_id = update.effective_user.id
    user_message = update.message.text.strip()
    
    if not user_message:
        await update.message.reply_text(
            "I didn't catch that\\. Please type a valid message\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    
    logger.info(f"User ({user_id}): {user_message}")
    
    # Ensure chat history exists
    if user_id not in chat_histories:
        initialize_chat_history(user_id)
    
    chat_histories[user_id].append(structure_message(ROLE_USER, user_message))
    trim_chat_history(user_id)  # Maintain history limit
    
    await update.message.chat.send_action(action="typing")  # Indicate bot is responding
    
    try:
        full_prompt = "\n".join([msg['content'] for msg in chat_histories[user_id]])
        response_text = generate_content(full_prompt)
        
        if not response_text:
            response_text = "I'm not sure how to respond\\. Can you rephrase your question?"
        
        chat_histories[user_id].append(structure_message(ROLE_ASSISTANT, response_text))
        trim_chat_history(user_id)
        
        # Format the response with proper Markdown escaping
        formatted_response = MessageFormatter.format_response(response_text)
        
        logger.info(f"Bot response: {response_text}")
        await update.message.reply_text(
            formatted_response,
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except Exception as e:
        logger.error(f"Error generating response for user ({user_id}): {str(e)}")
        await update.message.reply_text(
            "Oops\\! Something went wrong\\. Please try again later\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )