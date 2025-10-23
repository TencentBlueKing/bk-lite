# OpsPilot ChatFlow Integration Documentation

Trigger methods are the "switches" that start a Chatflow (chat workflow). Choosing different trigger methods determines how the workflow starts, who initiates it, and what scenarios it applies to. **Scheduled triggers, RESTful API, and OpenAI API** - these three methods complement each other, enabling Chatflow to adapt to various needs from simple automation to complex system integration.

## Trigger Method 1: Scheduled Trigger

Scheduled trigger is a very powerful and commonly used trigger method in automated workflows. It allows your workflow (Chatflow) to automatically start running at **specific time points** or according to **fixed time intervals** without any manual operation. It uses a time schedule (similar to an alarm clock or cron job) as the "switch" to start the workflow. When the system time meets your preset conditions, the system will automatically create a new workflow instance and begin execution. Whether it's simple daily reminders or complex data processing tasks, scheduled triggers can provide you with precise, reliable, and efficient automated startup solutions, making workflows run as precisely as Swiss clockwork, becoming an indispensable automation cornerstone in enterprise digital transformation.

## Trigger Method 2: RESTful API

RESTful API allows you to **publish a workflow (Chatflow) as a standard API interface**, making it callable by any system, application, or service capable of sending HTTP requests. Simply put, it generates a unique URL address (commonly called a **Webhook URL** or **Endpoint**) for the Chatflow. Users with permissions to this chatflow workspace can trigger the execution of the Chatflow immediately by sending a POST request. RESTful API trigger is not just a technical feature, but a strategic interface for enterprise digital transformation. It upgrades workflows from closed automation tools to open digital business hubs, allowing every creative idea to quickly connect with the world and every innovation to easily integrate resources.

Example:

Body parameters: {"user_message": "Help me check the server status"}

RESTful API request URL: <http://bklite.canwya.net/api/v1/opspilot/bot_mgmt/execute_chat_flow/?bot_id=1&node_id=abcdef>

(The request URL for the trigger node can be viewed in the corresponding node after saving the canvas)

## Trigger Method 3: OpenAI API

OpenAI API essentially mounts Chatflow directly into **OpenAI's model ecosystem**, allowing workflows to be triggered and run by calling OpenAI's API (such as ChatGPT, GPT-4). Simply put, it allows you to create a **custom GPT action** or a **dedicated model callable by OpenAI API**. When users chat with GPT, or when calling a specific OpenAI model in code, the request is not sent to the generic ChatGPT, but is routed to a pre-designed Chatflow. After the Chatflow processes the request, it returns the result, which is then presented to the user by OpenAI. OpenAI API trigger is not just a technical feature, but a key entry point for enterprises into the AI-native era. It transforms professional capabilities into AI-understandable and executable digital services, allowing every enterprise to have a 7×24 hour tireless intelligent employee team.

Example:

Body parameters: {"user_message": "Help me check the server status"}

OpenAI API request URL: <http://bklite.canwya.net/api/v1/opspilot/bot_mgmt/execute_chat_flow/?bot_id=1&node_id=abcdef>

(The request URL for the trigger node can be viewed in the corresponding node after saving the canvas)
