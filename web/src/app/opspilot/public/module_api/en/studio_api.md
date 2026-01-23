# OpsPilot ChatFlow Integration Documentation

Trigger methods are the "switches" that start a Chatflow (chat workflow). Choosing different trigger methods determines how the workflow starts, who initiates it, and what scenarios it applies to. **Scheduled triggers, RESTful API, OpenAI API, AG-UI, and Embedded Chat** - these methods complement each other, enabling Chatflow to adapt to various needs from simple automation to complex system integration.

## Trigger Method 1: Scheduled Trigger

Scheduled trigger is a very powerful and commonly used trigger method in automated workflows. It allows your workflow (Chatflow) to automatically start running at **specific time points** or according to **fixed time intervals** without any manual operation. It uses a time schedule (similar to an alarm clock or cron job) as the "switch" to start the workflow. When the system time meets your preset conditions, the system will automatically create a new workflow instance and begin execution. Whether it's simple daily reminders or complex data processing tasks, scheduled triggers can provide you with precise, reliable, and efficient automated startup solutions, making workflows run as precisely as Swiss clockwork, becoming an indispensable automation cornerstone in enterprise digital transformation.

## Trigger Method 2: RESTful API

RESTful API allows you to **publish a workflow (Chatflow) as a standard API interface**, making it callable by any system, application, or service capable of sending HTTP requests. Simply put, it generates a unique URL address (commonly called a **Webhook URL** or **Endpoint**) for the Chatflow. Users with permissions to this chatflow workspace can trigger the execution of the Chatflow immediately by sending a POST request. RESTful API trigger is not just a technical feature, but a strategic interface for enterprise digital transformation. It upgrades workflows from closed automation tools to open digital business hubs, allowing every creative idea to quickly connect with the world and every innovation to easily integrate resources.

Example:

Body parameters: {"user_message": "Help me check the server status"}

RESTful API request URL: <http://bklite.canwya.net/api/v1/opspilot/bot_mgmt/execute_chat_flow/${bot_id}/${node_id}/>

(The request URL for the trigger node can be viewed in the corresponding node after saving the canvas)

## Trigger Method 3: OpenAI API

OpenAI API essentially mounts Chatflow directly into **OpenAI's model ecosystem**, allowing workflows to be triggered and run by calling OpenAI's API (such as ChatGPT, GPT-4). Simply put, it allows you to create a **custom GPT action** or a **dedicated model callable by OpenAI API**. When users chat with GPT, or when calling a specific OpenAI model in code, the request is not sent to the generic ChatGPT, but is routed to a pre-designed Chatflow. After the Chatflow processes the request, it returns the result, which is then presented to the user by OpenAI. OpenAI API trigger is not just a technical feature, but a key entry point for enterprises into the AI-native era. It transforms professional capabilities into AI-understandable and executable digital services, allowing every enterprise to have a 7×24 hour tireless intelligent employee team.

Example:

Body parameters: {"user_message": "Help me check the server status"}

OpenAI API request URL: <http://bklite.canwya.net/api/v1/opspilot/bot_mgmt/execute_chat_flow/${bot_id}/${node_id}/>

(The request URL for the trigger node can be viewed in the corresponding node after saving the canvas)

## Trigger Method 4: AG-UI

AG-UI (Agent User Interface) trigger method is a triggering mechanism specifically designed for intelligent agent conversation interfaces. It seamlessly integrates Chatflow into the **AG-UI conversation system**, enabling users to interact with workflows through natural language via a unified agent interface. Simply put, it creates a **dedicated conversation entry point** for the Chatflow. When users initiate a conversation in the AG-UI interface, the system automatically routes to the corresponding Chatflow for processing. The core advantage of the AG-UI trigger method lies in providing a consistent user experience and intelligent interaction approach, allowing users to complete complex business operations through natural conversation without worrying about the underlying workflow logic. This trigger method is particularly suitable for scenarios that require frequent human-machine interaction and high user experience requirements. AG-UI trigger is not just a technical interface, but an important bridge for enterprises to build intelligent service experiences. It encapsulates complex workflows into simple conversational interactions, allowing every employee to easily use the enterprise's automation capabilities as if chatting with colleagues, truly achieving AI-driven digital transformation.

Example:

Body parameters: {"user_message": "Help me check the server status"}

AG-UI request URL: <http://bklite.canwya.net/api/v1/opspilot/bot_mgmt/execute_chat_flow/${bot_id}/${node_id}/>

(The request URL for the trigger node can be viewed in the corresponding node after saving the canvas)

## Trigger Method 5: Embedded Chat

Embedded Chat trigger method is a web-embedded conversation window based on the **AG-UI protocol**. It allows you to embed Chatflow directly into any web page as a **conversation component**, providing instant intelligent conversation services to website visitors. Through simple JavaScript code snippets, you can display a conversation window at any position on the web page or as a floating button. Users can interact with the Chatflow in real-time after clicking. This trigger method is particularly suitable for scenarios that require real-time customer support or intelligent assistant services, such as corporate websites, product pages, online documentation, and internal systems. Embedded Chat not only lowers the integration barrier but also provides flexible style customization and data transmission capabilities, allowing enterprises to provide a smooth conversation experience while maintaining brand consistency. Embedded Chat trigger is the front-end entry point for enterprises to build an intelligent user service system. It presents powerful workflow capabilities to end users in the most user-friendly way, truly achieving a "what you see is what you get" intelligent service experience.

### Embed Code Example

Add the following code to your web page HTML (recommended to place before the `</body>` tag):

```html
<script>
  !(function () {
    let e = document.createElement("link"),
      s = document.createElement("script"),
      t = document.head || document.getElementsByTagName("head")[0];
    
    // Load styles
    (e.rel = "stylesheet"),
    (e.href = "https://cdn.example.com/webchat/dist/browser/style.css"),
    t.appendChild(e);
    
    // Load script
    (s.src = "https://cdn.example.com/webchat/dist/browser/webchat.js"),
    (s.async = !0),
    (s.onload = () => {
      if (window.WebChat && window.WebChat.default) {
        window.WebChat.default(
          {
            sseUrl: "http://bklite.canwya.net/api/v1/opspilot/bot_mgmt/execute_chat_flow/?bot_id=1&node_id=abcdef",
            title: "Smart Assistant",
            theme: "light",  // Options: light / dark
            customData: { page: document.title }
          },
          null  // null = floating button mode, or pass DOM element for inline embedding
        );
      }
    }),
    (s.onerror = () => {
      console.error("Failed to load WebChat");
    }),
    t.appendChild(s);
  })();
</script>
```

### Configuration Parameters

- **sseUrl**: SSE streaming request URL for Chatflow (The request URL for the trigger node can be viewed in the corresponding node after saving the canvas)
- **title**: Conversation window title
- **theme**: Theme style, supports `light` or `dark`
- **customData**: Custom data that will be sent to Chatflow with the request
- **Second parameter**: 
  - `null` - Display as a floating button in the bottom right corner of the page
  - DOM element - Inline embed the conversation window into the specified HTML element

### Use Cases

- Online customer service for corporate websites
- Intelligent Q&A assistant for product documentation
- Operation guidance for internal systems
- Shopping consultation for e-commerce websites
- User support for SaaS products
