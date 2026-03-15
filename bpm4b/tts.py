import os
import re
import uuid
import logging
from kokoro import KModel, KPipeline
import soundfile as sf
import numpy as np

logger = logging.getLogger(__name__)

# Initialize model (lazy loading)
_pipeline = None

def get_pipeline():
    global _pipeline
    if _pipeline is None:
        logger.info("Initializing Kokoro TTS Pipeline...")
        _pipeline = KPipeline(lang_code='a')  # Default to US English
    return _pipeline

def split_text_into_chunks(text, max_length=1000):
    """Split text into manageable chunks for TTS"""
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    # Simple split by punctuation or newlines
    sentences = re.split(r'(?<=[.!?])\s+|\n+', text)
    
    current_chunk = ""
    for sentence in sentences:
        if len(current_chunk) + len(sentence) < max_length:
            current_chunk += sentence + " "
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence + " "
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks

def generate_tts(text, output_path, voice='af_heart', speed=1.0):
    """Generate audio from text using Kokoro"""
    try:
        pipeline = get_pipeline()
        
        # Generator yields (graphemes, phonemes, audio)
        generator = pipeline(
            text, voice=voice, 
            speed=speed, split_pattern=r'\n+'
        )
        
        all_audio = []
        for gs, ps, audio in generator:
            all_audio.append(audio)
            
        if not all_audio:
            raise Exception("No audio generated")
            
        # Concatenate all audio segments
        combined_audio = np.concatenate(all_audio)
        
        # Save as WAV
        sf.write(output_path, combined_audio, 24000)
        return True
    except Exception as e:
        logger.error(f"TTS Generation error: {e}")
        raise
