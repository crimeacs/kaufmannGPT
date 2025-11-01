"""
Visual Audience Analyzer
Captures images and analyzes audience reaction and environment using OpenAI's vision API
Compatible with the main KaufmannGPT application architecture
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Dict, Any, AsyncGenerator
import cv2
import base64
import aiohttp

class VisualAudienceAnalyzer:
    """
    Analyzes audience reactions using image capture and OpenAI vision API
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the visual audience analyzer
        
        Args:
            config: Configuration dictionary containing API keys and settings
        """
        self.api_key = config.get('openai_api_key')
        self.model = config.get('visual_model', 'gpt-4o')
        self.camera_index = config.get('camera_index', 0)
        self.api_url = config.get('openai_api_url', 'https://api.openai.com/v1/chat/completions')
        self.analysis_interval = config.get('visual_analysis_interval', 1.0)
        
        self.logger = logging.getLogger(__name__)
        self.is_running = False
        self.current_reaction = "neutral"
        
        # JSON schema for structured response
        self.json_schema = {
            "type": "object",
            "properties": {
                "audience_reaction": {
                    "type": "string",
                    "description": "Description of how the audience is reacting."
                },
                "environment_looks_like": {
                    "type": "string", 
                    "description": "Description of what the environment looks like."
                }
            },
            "required": ["audience_reaction", "environment_looks_like"],
            "additionalProperties": False
        }

    def capture_image(self) -> str:
        """
        Capture image from camera and return as base64 encoded string
        
        Returns:
            Base64 encoded image string
        """
        cap = cv2.VideoCapture(self.camera_index)
        
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open camera {self.camera_index}")
        
        try:
            ret, frame = cap.read()
            if not ret:
                raise RuntimeError("Failed to capture image from camera")
            
            # Encode image to base64
            _, buffer = cv2.imencode('.jpg', frame)
            image_base64 = base64.b64encode(buffer).decode('utf-8')
            
            return image_base64
            
        finally:
            cap.release()

    async def analyze_image(self, image_base64: str) -> Dict[str, Any]:
        """
        Analyze image using OpenAI vision API
        
        Args:
            image_base64: Base64 encoded image
            
        Returns:
            Dictionary with audience_reaction and environment_looks_like
        """
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Analyse the image and make a JSON with description of the audience and environment.\n– For the \"audience_reaction\" you MUST focus on audiences images;\n– For the \"environment_looks_like\" describing how it looks like"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "audience_and_environment",
                    "strict": True,
                    "schema": self.json_schema
                }
            },
            "max_tokens": 300
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        result_data = await response.json()
                        content = result_data['choices'][0]['message']['content']
                        
                        result = json.loads(content)
                        result["timestamp"] = datetime.now().isoformat()
                        
                        # Update current reaction state
                        self.current_reaction = result.get('audience_reaction', 'neutral')
                        
                        self.logger.info(f"Visual analysis result: {result}")
                        return result
                    else:
                        error_text = await response.text()
                        self.logger.error(f"API error: {response.status} - {error_text}")
                        raise RuntimeError(f"Visual analysis API error: {response.status}")
                        
        except Exception as e:
            self.logger.error(f"Error analyzing image: {e}")
            raise

    async def start_analysis(self) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Start continuous image capture and analysis
        Captures images every second and analyzes them
        
        Yields:
            Analysis results with audience_reaction and environment_looks_like
        """
        self.is_running = True
        self.logger.info("Starting visual audience analysis...")
        
        try:
            while self.is_running:
                start_time = time.time()
                
                try:
                    # Capture from camera and analyze
                    image_base64 = self.capture_image()
                    analysis = await self.analyze_image(image_base64)
                    yield analysis
                    
                except Exception as e:
                    self.logger.error(f"Error in visual analysis loop: {e}")
                    # Continue loop even if one analysis fails
                
                # Wait for next interval (1 second as specified)
                elapsed_time = time.time() - start_time
                sleep_time = max(0, self.analysis_interval - elapsed_time)
                await asyncio.sleep(sleep_time)
                
        except KeyboardInterrupt:
            self.logger.info("Visual analysis interrupted by user")
        finally:
            self.is_running = False
            self.logger.info("Stopped visual audience analysis")

    def stop_analysis(self):
        """Stop the analysis loop"""
        self.is_running = False

    async def analyze_single_image(self, image_path: str = None) -> Dict[str, Any]:
        """
        Analyze a single image file or capture from camera
        
        Args:
            image_path: Path to image file. If None, captures from camera
            
        Returns:
            Analysis result dictionary
        """
        if image_path:
            # Read image from file
            with open(image_path, 'rb') as image_file:
                image_base64 = base64.b64encode(image_file.read()).decode('utf-8')
        else:
            # Capture from camera
            image_base64 = self.capture_image()
            
        return await self.analyze_image(image_base64)


async def main():
    """
    Example usage of the VisualAudienceAnalyzer
    """
    import os
    import yaml
    
    # Load config similar to main app
    config = {
        'openai_api_key': os.getenv("OPENAI_API_KEY"),
        'visual_model': 'gpt-4o',
        'camera_index': 0,
        'visual_analysis_interval': 1.0
    }
    
    if not config['openai_api_key']:
        print("Please set OPENAI_API_KEY environment variable")
        return
        
    analyzer = VisualAudienceAnalyzer(config)
    
    print("Starting visual audience analysis... Press Ctrl+C to stop")
    
    try:
        async for analysis in analyzer.start_analysis():
            print(f"\n--- Analysis at {analysis['timestamp']} ---")
            print(f"Audience Reaction: {analysis['audience_reaction']}")
            print(f"Environment: {analysis['environment_looks_like']}")
            
    except KeyboardInterrupt:
        print("\nStopping analysis...")
        analyzer.stop_analysis()


if __name__ == "__main__":
    asyncio.run(main())