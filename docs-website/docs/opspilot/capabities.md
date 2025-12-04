---
sidebar_position: 3
---

# 内置能力

汇总介绍 OpsPilot 中的各种内置能力，详细解析其作用。

## 模型

在这一块内容中，将详细介绍各个模型的类型、功能、应用场景等，帮助用户选用模型。

### LLM模型

#### HuggingFace系列

##### QwQ（阿里云通义千问推理模型）

- **核心功能**：通过强化学习提升数学、编程和逻辑推理能力，能用 “思考链” 逐步分析问题。
- **优势**：
  - 小而强：仅 320 亿参数（约 3.2 亿个 “知识节点”），性能却接近 6700 亿参数的 DeepSeek-R1 模型。
  - 多领域精通：数学题解答、代码生成、复杂逻辑推理（如合同条款分析）都能胜任。
- **作用**：
  - 数学推理：能解决复杂的数学问题，例如解答高难度的代数方程、几何证明题等。当你遇到一道复杂的数列推理题，它可以逐步分析推理过程，给出正确答案。
  - 编程辅助：帮助编写代码、调试代码以及对代码进行逻辑优化。如果你在编写一个 Python 程序时遇到逻辑错误，它可以帮你找出问题并提供解决方案。
  - 通用推理：处理各类需要逻辑思考的问题，如合同条款解读、逻辑谜题解答等。

#### DeepSeek 系列（国产高效模型）

##### DeepSeek-R1:1.5b

- **核心功能**：专注于代码领域的轻量级大语言模型，支持 Python、Java 等编程语言。
- **优势**：
  - 低配置运行：手机或普通电脑（8GB 内存）即可使用，不占资源。
  - 代码生成快：补全代码、生成函数、调试错误，速度比人工快 3-5 倍。
- **作用**：
  - 代码生成：根据需求快速生成各种编程语言的代码，如 Python、Java、C++ 等。如果你需要写一个简单的 Web 爬虫程序，它可以快速为你生成相应的 Python 代码。
  - 代码优化：对已有的代码进行优化，提高代码的运行效率和可读性。比如优化一个排序算法的代码，让它在处理大规模数据时速度更快。
  - 代码纠错：检查代码中的语法错误和逻辑错误，并给出修正建议。

#### OpenAI 系列（全球领先的通用模型）

##### 1. GPT-3.5-Turbo-16K

- **核心功能**：具有较长上下文处理能力的通用大语言模型，长文本处理（1.2 万字），性价比高。
- **优势**：
  - 多任务适配：写文章、翻译、数据分析、客服问答都能做。
  - 性价比高：在性能和成本之间取得了较好的平衡，相比于 GPT-4，使用成本更低，适合大多数企业和个人用户。
- **作用**：
  - 内容创作平台：在一些自媒体平台上，创作者可以利用它快速生成文章的大纲和初稿，提高创作效率。
  - 企业文档处理：企业在处理大量的文档时，如合同、报告等，可以使用它进行内容总结和关键信息提取。

##### 2. GPT-4-32K

- **核心功能**：具有超长上下文处理能力和强大多模态能力的顶级大语言模型。超长文本处理（2.4 万字），支持多模态（文本 + 图像）。
- **优势**：
  - 强大的综合能力：在语言理解、推理能力、创意生成等方面都表现出色，是目前最先进的大语言模型之一。
  - 多模态融合：打破了传统语言模型只能处理文本的限制，实现了文本和图像的融合交互，拓展了应用场景。
- **作用**：
  - 超长文本分析：能够处理长达 32K tokens 的文本，对超长篇幅的文档进行深入分析和理解，如对一部长篇小说进行情节分析和主题探讨。
  - 多模态交互：支持文本和图像的输入和输出，例如可以根据输入的图片生成相关的文字描述，或者根据文字描述生成图像。
  - 复杂问题解决：解决各种复杂的问题，包括高难度的数学问题、专业领域的技术问题等。

##### 3. GPT-4o（多模态全能模型）

- **核心功能**：旗舰级多模态模型，支持文本、音频、图像、视频的混合输入输出，主打 “全能交互” 能力。
- **优势**：
  - 速度与成本革新：处理速度提升 200%，价格降低 50%，速率限制提高 5 倍，兼顾高效与低成本。
  - 多模态能力突破：视觉上能精准识别图像视频细节，语音可直接交互且能识别情绪、模拟声音，还能实现跨模态融合创作。
  - 推理能力提升：在 0-shot COT MMLU 和传统的 5-shot no-CoT MMLU 评估中设定新高分，展现强大推理性能。
- **作用**：
  - 实时多模态推理：能同时对音频、视觉和文本进行实时推理，实现多模态信息的同步处理。
  - 跨语言翻译：可处理 50 种不同语言，满足全球不同语言人群间的交流翻译需求。
  - 复杂任务处理：具备强大的文本、推理和编码能力，能应对代码生成、数据分析等复杂工作。

#### LLM模型汇总

目前opspilot支持的大模型除了上述外，全量见下表

| 分类名称 | 模型图标 | 模型ID | 模型名称 | 模型类别 |
| --- | --- | --- | --- | --- |
| Baichuan（百川） | Baichuan | baichuan-2 | Baichuan 2 | 文本类 |
| Baichuan（百川） | Baichuan | baichuan-2-chat | Baichuan 2 Chat | 文本类 |
| CodeLlama | MetaAI | code-llama | CodeLlama | 代码类 |
| CodeLlama | MetaAI | code-llama-instruct | CodeLlama Instruct | 代码类 |
| CodeLlama | MetaAI | code-llama-python | CodeLlama Python | 代码类 |
| CodeGeeX | CodeGeeX | codegeex4 | CodeGeeX4 | 代码类 |
| CodeQwen | Alibaba | codeqwen1.5 | CodeQwen1.5 | 代码类 |
| CodeQwen | Alibaba | codeqwen1.5-chat | CodeQwen1.5 Chat | 代码类 |
| CodeShell |  | codeshell | CodeShell | 代码类 |
| CodeShell |  | codeshell-chat | CodeShell Chat | 代码类 |
| Codestral | Mistral | codestral-v0.1 | Codestral v0.1 | 代码类 |
| CogAgent | Zhipu | cogagent | CogAgent | 推理增强 |
| DeepSeek | DeepSeek | deepseek | DeepSeek | 推理增强 |
| DeepSeek | DeepSeek | deepseek-chat | DeepSeek Chat | 推理增强 |
| DeepSeek | DeepSeek | deepseek-coder | DeepSeek Coder | 代码类 |
| DeepSeek | DeepSeek | deepseek-coder-instruct | DeepSeek Coder Instruct | 代码类 |
| DeepSeek | DeepSeek | deepseek-prover-v2 | DeepSeek Prover v2 | 推理增强 |
| DeepSeek | DeepSeek | deepseek-r1 | DeepSeek R1 | 推理增强 |
| DeepSeek | DeepSeek | deepseek-r1-0528 | DeepSeek R1 0528 | 推理增强 |
| DeepSeek | DeepSeek | deepseek-r1-0528-qwen3 | DeepSeek R1 0528 Qwen3 | 推理增强 |
| DeepSeek | DeepSeek | deepseek-r1-distill-llama | DeepSeek R1 Distill Llama | 推理增强 |
| DeepSeek | DeepSeek | deepseek-r1-distill-qwen | DeepSeek R1 Distill Qwen | 推理增强 |
| DeepSeek | DeepSeek | deepseek-v2-chat | DeepSeek V2 Chat | 推理增强 |
| DeepSeek | DeepSeek | deepseek-v2-chat-0628 | DeepSeek V2 Chat 0628 | 推理增强 |
| DeepSeek | DeepSeek | deepseek-v2.5 | DeepSeek V2.5 | 推理增强 |
| DeepSeek | DeepSeek | deepseek-v3 | DeepSeek V3 | 推理增强 |
| DeepSeek | DeepSeek |deepseek-v3-0324 | DeepSeek V3 0324 | 推理增强 |
| DeepSeek | DeepSeek | deepseek-vl2 | DeepSeek VL2 | 多模态 |
| DianJin |  | DianJin-R1 | DianJin R1 | 推理增强 |
| ERNIE | Baidu | Ernie4.5 | ERNIE 4.5 | 文本类 |
| FinLLM |  | fin-r1 | Fin R1 | 推理增强 |
| Gemma | Gemma | gemma-3-1b-it | Gemma 3 1B IT | 文本类 |
| Gemma | Gemma | gemma-3-it | Gemma 3 IT | 文本类 |
| GLM（智谱） | ChatGLM | glm-4.1v-thinking | GLM 4.1V Thinking | 推理增强 |
| GLM（智谱） | ChatGLM | glm-4.5 | GLM 4.5 | 文本类 |
| GLM（智谱） | ChatGLM | glm-4v | GLM 4V | 文本类 |
| GLM（智谱） | ChatGLM | glm-edge-chat | GLM Edge Chat | 文本类 |
| GLM（智谱） | ChatGLM | glm4-0414 | GLM4 0414 | 文本类 |
| GLM（智谱） | ChatGLM | glm4-chat | GLM4 Chat | 文本类 |
| GLM（智谱） | ChatGLM | glm4-chat-1m | GLM4 Chat 1M | 文本类 |
| Gorilla |  | gorilla-openfunctions-v2 | Gorilla OpenFunctions v2 | 推理增强 |
| OpenAI | GPT | gpt-2 | GPT-2 | 文本类 |
| HuatuoGPT |  | HuatuoGPT-o1-LLaMA-3.1 | HuatuoGPT o1 LLaMA 3.1 | 文本类 |
| HuatuoGPT |  | HuatuoGPT-o1-Qwen2.5 | HuatuoGPT o1 Qwen2.5 | 文本类 |
| InternLM | Intern | internlm3-instruct | InternLM3 Instruct | 文本类 |
| InternVL |  | InternVL3 | InternVL3 | 文本类 |
| LLaMA | Meta | llama-2 | LLaMA 2 | 文本类 |
| LLaMA | Meta | llama-2-chat | LLaMA 2 Chat | 文本类 |
| LLaMA | Meta | llama-3 | LLaMA 3 | 文本类 |
| LLaMA | Meta | llama-3-instruct | LLaMA 3 Instruct | 文本类 |
| LLaMA | Meta | llama-3.1 | LLaMA 3.1 | 文本类 |
| LLaMA | Meta | llama-3.1-instruct | LLaMA 3.1 Instruct | 文本类 |
| LLaMA | Meta | llama-3.2-vision | LLaMA 3.2 Vision | 多模态 |
| LLaMA | Meta | llama-3.2-vision-instruct | LLaMA 3.2 Vision Instruct | 多模态 |
| LLaMA | Meta | llama-3.3-instruct | LLaMA 3.3 Instruct | 文本类 |
| Marco |  | marco-o1 | Marco o1 | 文本类 |
| MiniCPM |  | minicpm-2b-dpo-bf16 | MiniCPM 2B DPO BF16 | 文本类 |
| MiniCPM |  | minicpm-2b-dpo-fp16 | MiniCPM 2B DPO FP16 | 文本类 |
| MiniCPM |  | minicpm-2b-dpo-fp32 | MiniCPM 2B DPO FP32 | 文本类 |
| MiniCPM |  | minicpm-2b-sft-bf16 | MiniCPM 2B SFT BF16 | 文本类 |
| MiniCPM |  | minicpm-2b-sft-fp32 | MiniCPM 2B SFT FP32 | 文本类 |
| MiniCPM |  | MiniCPM-V-2.6 | MiniCPM V 2.6 | 文本类 |
| MiniCPM |  | minicpm3-4b | MiniCPM3 4B | 文本类 |
| MiniCPM |  | minicpm4 | MiniCPM4 | 文本类 |
| Mistral | Mistral | mistral-instruct-v0.1 | Mistral Instruct v0.1 | 文本类 |
| Mistral | Mistral | mistral-instruct-v0.2 | Mistral Instruct v0.2 | 文本类 |
| Mistral | Mistral | mistral-instruct-v0.3 | Mistral Instruct v0.3 | 文本类 |
| Mistral | Mistral | mistral-large-instruct | Mistral Large Instruct | 文本类 |
| Mistral | Mistral | mistral-nemo-instruct | Mistral NeMo Instruct | 文本类 |
| Mistral | Mistral | mistral-v0.1 | Mistral v0.1 | 文本类 |
| Mixtral | Mistral | mixtral-8x22B-instruct-v0.1 | Mixtral 8x22B Instruct v0.1 | 文本类 |
| Mixtral | Mistral | mixtral-instruct-v0.1 | Mixtral Instruct v0.1 | 文本类 |
| Mixtral | Mistral | mixtral-v0.1 | Mixtral v0.1 | 文本类 |
| Moonlight |  | moonlight-16b-a3b-instruct | Moonlight 16B A3B Instruct | 文本类 |
| OpenHermes |  | openhermes-2.5 | OpenHermes 2.5 | 文本类 |
| OPT |  | opt | OPT | 文本类 |
| Orion |  | orion-chat | Orion Chat | 文本类 |
| Ovis |  | Ovis2 | Ovis2 | 文本类 |
| Phi |  | phi-2 | Phi-2 | 文本类 |
| Phi | | Phi-3 |Mini 128K Instruct | 文本类 |
| Phi |  | phi-3-mini-4k-instruct | Phi-3 Mini 4K Instruct | 文本类 |
| QvQ |  | QvQ-72B-Preview | QvQ 72B Preview | 文本类 |
| Qwen（千问） | Qwen | qwen-chat | Qwen Chat | 文本类 |
| Qwen（千问） | Qwen | qwen1.5-chat | Qwen1.5 Chat | 文本类 |
| Qwen（千问） | Qwen | qwen1.5-moe-chat | Qwen1.5 MoE Chat | 文本类 |
| Qwen（千问） | Qwen | qwen2-audio | Qwen2 Audio | 多模态 |
| Qwen（千问） | Qwen | qwen2-audio-instruct | Qwen2 Audio Instruct | 多模态 |
| Qwen（千问） | Qwen | qwen2-instruct | Qwen2 Instruct | 文本类 |
| Qwen（千问） | Qwen | qwen2-moe-instruct | Qwen2 MoE Instruct | 文本类 |
| Qwen（千问） | Qwen | qwen2-vl-instruct | Qwen2 VL Instruct | 多模态 |
| Qwen（千问） | Qwen | qwen2.5 | Qwen2.5 | 文本类 |
| Qwen（千问） | Qwen | qwen2.5-coder | Qwen2.5 Coder | 代码类 |
| Qwen（千问） | Qwen | qwen2.5-coder-instruct | Qwen2.5 Coder Instruct | 代码类 |
| Qwen（千问） | Qwen | qwen2.5-instruct | Qwen2.5 Instruct | 文本类 |
| Qwen（千问） | Qwen | qwen2.5-instruct-1m | Qwen2.5 Instruct 1M | 文本类 |
| Qwen（千问） | Qwen | qwen2.5-omni | Qwen2.5 Omni | 多模态 |
| Qwen（千问） | Qwen | qwen2.5-vl-instruct | Qwen2.5 VL Instruct | 多模态 |
| Qwen（千问） | Qwen | qwen3 | Qwen3 | 文本类 |
| Qwen（千问） | Qwen | Qwen3-Coder | Qwen3 Coder | 代码类 |
| Qwen（千问） | Qwen | Qwen3-Instruct | Qwen3 Instruct | 文本类 |
| Qwen（千问） | Qwen | Qwen3-Thinking | Qwen3 Thinking | 推理增强 |
| Qwen（千问） | Qwen | qwenLong-l1 | QwenLong L1 | 文本类 |
| QwQ |  | QwQ-32B | QwQ 32B | 文本类 |
| QwQ |  | QwQ-32B-Preview | QwQ 32B Preview | 文本类 |
| SEALLM |  | seallm_v2 | SEALLM v2 | 文本类 |
| SEALLM |  | seallm_v2.5 | SEALLM v2.5 | 文本类 |
| SEALLM |  | seallms-v3 | SEALLMS v3 | 文本类 |
| Skywork |  | Skywork | Skywork | 文本类 |
| Skywork |  | Skywork-Math | Skywork Math | 推理增强 |
| Skywork |  | skywork-or1 | Skywork OR1 | 推理增强 |
| Skywork |  | skywork-or1-preview | Skywork OR1 Preview | 推理增强 |
| Telechat |  | telechat | Telechat | 文本类 |
| TinyLlama |  | tiny-llama | Tiny Llama | 文本类 |
| WizardCoder |  | wizardcoder-python-v1.0 | WizardCoder Python v1.0 | 代码类 |
| WizardMath |  | wizardmath-v1.0 | WizardMath v1.0 | 推理增强 |
| XiYanSQL |  | XiYanSQL-QwenCoder-2504 | XiYanSQL QwenCoder 2504 | 代码类 |
| Xverse |  | xverse | Xverse | 文本类 |
| Xverse |  | xverse-chat | Xverse Chat | 文本类 |
| Yi（零一万物） | Yi | Yi | Yi | 文本类 |
| Yi（零一万物） | Yi | Yi-1.5 | Yi 1.5 | 文本类 |
| Yi（零一万物） | Yi | Yi-1.5-chat | Yi 1.5 Chat | 文本类 |
| Yi（零一万物） | Yi | Yi-1.5-chat-16k | Yi 1.5 Chat 16k | 文本类 |
| Yi（零一万物） | Yi | Yi-200k | Yi 200k | 文本类 |
| Yi（零一万物） | Yi | Yi-chat | Yi Chat | 文本类 |

### Embed 模型

#### FastEmbed（bge-small-zh-v1.5）

核心功能

轻量化中文语义嵌入模型，专注于将中文文本转化为计算机可理解的“数字编码”，高效捕捉语义相似性。

优势

- **轻量快速**：仅 95MB 大小，普通电脑也能运行，处理速度毫秒级响应，适合实时场景。
- **中文专精**：深度优化中文语义，精准识别成语、网络用语、专业术语（如法律、医疗词汇），语义匹配更准确。
- **低成本易用**：开源免费，无需复杂配置，直接集成到搜索、推荐等系统中降低开发成本。

作用

- **文本语义转化**：将中文句子/段落转化为高维向量，让计算机“理解”文字含义（如区分“打折”和“促销”的语义相似性）。
- **高效语义检索**：在海量文本中快速定位语义匹配内容（如用户输入“天气太热怎么办”，找到相关解暑攻略）。
- **智能系统赋能**：为客服、推荐、文档管理等系统提供语义支持，提升信息处理精度。

#### BCEmbedding（bce-embedding-base_v1）

核心功能

中英双语语义桥梁模型，支持中文和英文文本的双向语义转化，打破跨语言理解壁垒。

优势

- **双语精准对齐**：基于有道翻译技术，中英语义向量高度匹配（如“人工智能”与“Artificial Intelligence”编码相近），跨语言检索准确率提升 40%。
- **长文本处理**：支持数万字文档（如合同、论文）的整体语义编码，避免碎片化信息丢失。
- **双阶段检索**：先快速筛选语义相关文本（缩小范围），再精准排序，提升复杂场景下的检索质量。

作用

- **跨语言语义映射**：将中文和英文文本转化为统一向量空间，实现双语语义“无缝对接”（如中文提问匹配英文文档）。
- **跨语言检索支持**：在中英混合文本库中，支持任意语言输入检索另一语言内容（如英文搜索找到中文产品说明）。
- **多语言系统增强**：为跨国企业、教育、电商等场景提供双语语义支持，优化跨语言信息处理效率。

#### 模型列表

| 品牌名 | 图标  模型ID| 模型名称 |
|------------------|----------|----------------------------------|------------------------------|
| 网易有道         |          | bce-embedding-base_v1           | BCE Embedding Base v1        | 可通过 ollama 部署：`ollama pull lrs33/bce-embedding-base_v1`           |
| BAAI (智源研究院) | BAAI     | bge-base-en                     | BGE Base English             |
| BAAI (智源研究院) | BAAI     | bge-base-en-v1.5                | BGE Base English v1.5        |
| BAAI (智源研究院) | BAAI     | bge-base-zh                     | BGE Base Chinese             |
| BAAI (智源研究院) | BAAI     | bge-base-zh-v1.5                | BGE Base Chinese v1.5        |
| BAAI (智源研究院) | BAAI     | bge-large-en                    | BGE Large English            |
| BAAI (智源研究院) | BAAI     | bge-large-en-v1.5               | BGE Large English v1.5       |
| BAAI (智源研究院) | BAAI     | bge-large-zh                    | BGE Large Chinese            |
| BAAI (智源研究院) | BAAI     | bge-large-zh-noinstruct         | BGE Large Chinese NoInstruct |
| BAAI (智源研究院) | BAAI     | bge-large-zh-v1.5               | BGE Large Chinese v1.5       |
| BAAI (智源研究院) | BAAI     | bge-m3                          | BGE M3                       |
| BAAI (智源研究院) | BAAI     | bge-small-en-v1.5               | BGE Small English v1.5       |
| BAAI (智源研究院) | BAAI     | bge-small-zh                    | BGE Small Chinese            |
| BAAI (智源研究院) | BAAI     | bge-small-zh-v1.5               | BGE Small Chinese v1.5       |
| 微软             |          | e5-large-v2                     | E5 Large v2                  |
| 阿里             | Alibaba  | gte-base                        | GTE Base                     |
| 阿里             | Alibaba  | gte-large                       | GTE Large                    |
| 阿里             | Alibaba  | gte-Qwen2                       | GTE Qwen2                    |
| Jina AI          | Jina     | jina-clip-v2                    | Jina CLIP v2                 |
| Jina AI          | Jina     | jina-embeddings-v2-base-en      | Jina Embeddings v2 Base EN   |
| Jina AI          | Jina     | jina-embeddings-v2-base-zh      | Jina Embeddings v2 Base ZH   |
| Jina AI          | Jina     | jina-embeddings-v2-small-en     | Jina Embeddings v2 Small EN  |
| Jina AI          | Jina     | jina-embeddings-v3              | Jina Embeddings v3           |
| Jina AI          | Jina     | jina-embeddings-v4              | Jina Embeddings v4           |
| Moka AI          |          | m3e-base                        | M3E Base                     |
| Moka AI          |          | m3e-large                       | M3E Large                    |ge                               |
| Moka AI          |          | m3e-small                       | M3E Small                    |
| 微软             |          | multilingual-e5-large           | Multilingual E5 Large        |
| 阿里             | Alibaba  | Qwen3-Embedding-0.6B            | Qwen3 Embedding 0.6B         |
| 阿里             | Alibaba  | Qwen3-Embedding-4B              | Qwen3 Embedding 4B           |
| 阿里             | Alibaba  | Qwen3-Embedding-8B              | Qwen3 Embedding 8B           |
| 赛博智能         |          | text2vec-base-chinese           | Text2Vec Base Chinese        |
| 赛博智能         |          | text2vec-base-chinese-paraphrase | Text2Vec Base Chinese Paraphrase |
| 赛博智能         |          | text2vec-base-chinese-sentence  | Text2Vec Base Chinese Sentence |
| 赛博智能         |          | text2vec-base-multilingual      | Text2Vec Base Multilingual   |
| 赛博智能         |          | text2vec-large-chinese          | Text2Vec Large Chinese       |

### Rerank 模型

#### BCEReranker（bce-reranker-base_v1）

核心功能

基于交叉编码器的中英日韩多语言重排序模型，专注于对初始检索结果进行精细化排序，提升信息检索的相关性和准确性。它与 BCEmbedding 模型形成"双阶段检索"组合，先通过 BCEmbedding 召回候选文档，再由 BCEReranker 对 Top 50-100 个结果进行重排，最终输出 Top 5-10 个高相关性片段。

优势

- **多语言跨域适配**：支持中文、英文、日文、韩文四语种，尤其在中英跨语言检索中表现突出（如中文查询匹配英文文档），适配教育、法律、金融、医疗等多领域数据。
- **长文本精准排序**：突破传统模型 512 Token 的输入限制，支持数万字文档的整体语义分析，有效处理合同、论文等长文本场景，避免碎片化信息干扰。
- **绝对分数过滤**：输出可量化的"绝对相关性分数"（推荐阈值 0.35-0.4），直接过滤低质量结果，减少 LLM 生成时的"幻觉"问题。
- **RAG 深度优化**：针对检索增强生成（RAG）场景设计，与 BCEmbedding 组合在 LlamaIndex 评测中达到 SOTA 水平，跨语言检索准确率提升 40%，MRR（平均倒数排名）提升 6.85%。

作用

- **检索结果精排**：对初始召回的文本片段进行二次排序，确保最相关内容优先展示（如用户搜索"人工智能发展趋势"，模型会优先展示最新政策文件而非过时资料）。
- **跨语言信息整合**：支持中英日韩混合检索，例如中文用户输入"气候变化应对措施"，模型可匹配英文国际协议、日文研究报告等多语言资源，实现跨语言知识融合。
- **长文档语义聚焦**：处理技术手册、法律条文等长文本时，精准定位与查询相关的段落（如搜索"合同违约责任"，直接跳转到对应条款而非全文检索），提升信息提取效率。
- **低质内容过滤**：通过绝对分数阈值（如 0.4）自动剔除不相关或低质量结果，减少 LLM 处理无效信息的耗时，优化整体响应速度。

---

#### rerank模型列表

| 品牌名  | 图标 | 模型| 模型名称 |
|------------------|----------|----------------------------------|------------------------------|
| 网易有道         |          | bce-reranker-base_v1            | BCE Reranker Base v1         |
| BAAI (智源研究院) | BAAI     | bge-reranker-base               | BGE Reranker Base            |
| BAAI (智源研究院) | BAAI     | bge-reranker-large              | BGE Reranker Large           |
| BAAI (智源研究院) | BAAI     | bge-reranker-v2-gemma           | BGE Reranker v2 Gemma        |
| BAAI (智源研究院) | BAAI     | bge-reranker-v2-m3              | BGE Reranker v2 M3           |
| BAAI (智源研究院) | BAAI     | bge-reranker-v2-minicpm-layerwise | BGE Reranker v2 MiniCPM Layerwise |
| Jina AI          | Jina     | jina-reranker-v2                | Jina Reranker v2             |
| OpenBMB          |          | minicpm-reranker                | MiniCPM Reranker             |
| 阿里             | Alibaba  | Qwen3-Reranker-0.6B             | Qwen3 Reranker 0.6B          |
| 阿里             | Alibaba  | Qwen3-Reranker-4B               | Qwen3 Reranker 4B            |
| 阿里             | Alibaba  | Qwen3-Reranker-8B               | Qwen3 Reranker 8B            |

---

### OCR 模型

#### OlmOCR

核心功能

基于大型语言模型的文档解析工具，专注于将 PDF、图像等非结构化文档转化为可编辑文本，支持表格、公式、手写内容的精准提取，尤其擅长处理复杂排版（如多栏布局、学术论文）。

优势

- **多模态融合**：结合语言模型（如 ChatGPT-4o、Qwen2-VL）与计算机视觉技术，通过上下文推理提升文本识别准确性，减少幻觉现象（如虚构内容）。
- **结构化输出**：保留文档原始格式（如表格、项目符号、边注），支持 Markdown 或 Dolma 格式输出，便于后续分析和编辑。
- **低成本高效**：开源工具包支持本地 GPU 部署，每处理 100 万页文档成本仅 190 美元，适合大规模文档数字化需求。

作用

- **学术与技术文档处理**：解析论文、技术手册中的公式、图表和多栏内容，生成结构化文本（如将 LaTeX 公式转换为可编辑格式）。
- **手写内容识别**：处理医疗记录、历史档案中的手写文字，准确率超 90%，支持 12 种语言的手写体识别。
- **PDF 数字化**：将扫描 PDF 转换为可搜索文本，保留原始排版，适用于法律合同、古籍修复等场景。

#### AzureOCR

核心功能

微软 Azure 云服务中的 OCR 工具，支持多语言文本识别（含手写和打印体），集成于表单识别器（Form Recognizer），可提取表格、发票、身份证等文档的结构化数据。

优势

- **云服务集成**：与 Azure AI 服务（如翻译、语言理解）无缝对接，支持 REST API 和低代码平台（如 Power Automate），快速部署至企业流程。
- **多语言与混合场景**：支持中文、英文、日文等 50+ 语言，可同时处理文档中的混合语言内容，适用于跨国企业的多语言数据管理。
- **高精度与安全**：基于深度学习模型，识别准确率高，且数据存储符合 ISO、GDPR 等合规标准，保障企业数据安全。

作用

- **表单自动化**：自动提取发票、报销单中的金额、日期等字段，减少人工录入错误（如将手写签名与打印文字分离识别）。
- **文档分析**：解析合同中的条款、身份证中的个人信息，生成结构化 JSON 数据，便于后续数据分析或 AI 模型训练。
- **实时处理**：支持实时视频流中的文本识别（如监控画面中的车牌、公告文字），适用于安防、物流等场景。

#### PaddleOCR

核心功能

百度开源的 OCR 工具包，提供端到端文本检测、识别和方向分类，支持 80+ 语言（含中文、日文、韩文），覆盖通用、金融、交通等多领域垂类模型。

优势

- **轻量与高效**：模型压缩技术（如 PP-OCRv4）将模型体积降至 8.5MB，移动端推理速度达毫秒级。
- **多语言与场景适配**：针对中文优化，支持复杂文本（如弯曲文字、低光照图像）。
- **开源与生态**：代码开源且文档完善，支持自定义训练和私有化部署。

作用

- **实时文本识别**：处理视频流或监控画面中的文字（如实时翻译路牌、提取视频字幕）。
- **文档管理**：批量处理扫描文档，提取关键信息（如合同中的甲方乙方、医疗报告中的诊断结果），提升办公效率。
- **跨语言支持**：实现中英日韩等多语言混合文本的识别与翻译，适用于跨境电商、教育等场景。

---

#### 模型汇总

| 模型      | 优势                                     | 作用                                   |
|-----------|------------------------------------------|----------------------------------------|
| OlmOCR    | 多模态融合，解析复杂排版（公式/手写），结构化输出 | 学术文档、手写档案、PDF 数字化处理       |
| AzureOCR  | 云服务集成，50+ 语言支持，安全合规           | 企业表单、合同解析，实时视频文本识别     |
| PaddleOCR | 轻量开源，80+ 语言（中文优化），端边云部署    | 移动端识别、批量文档处理、跨语言场景适配 |

---

## 工具

### 运维工具

#### Kubernetes Tools

介绍

Kubernetes 工具是一套针对 Kubernetes 集群的运维与管理工具，覆盖集群资源查询、状态监控、故障诊断及配置管理等功能，帮助用户高效管理容器化应用的部署、运行和维护。

作用

- **CI/CD 流程全链路管控**：
  - 任务可视化管理：通过列表清晰呈现 Jenkins 服务器上所有构建任务的名称、状态（启用/禁用）、最后构建时间及结果，便于团队快速定位异常任务（如连续失败的部署任务）。
  - 自动化触发与参数化构建：支持在触发构建时动态传入参数（如目标分支、环境变量、版本号），满足多环境（开发/测试/生产）差异化部署需求（例如：指定`--env=prod`触发生产环境构建）。

- **团队协作与流程审计**：
  - 构建任务追溯：通过任务列表快速查询历史构建记录，结合时间工具（如`get_current_time`）记录操作时间，形成完整的 CI/CD 审计日志（适用于金融、医疗等对合规性要求高的行业）。
  - 多工具集成支持：与代码仓库（Git）、制品仓库（Nexus）、监控系统（Prometheus）无缝对接，例如代码提交后自动触发 Jenkins 构建，构建完成后通过 Kubernetes 工具部署至集群，形成自动化流水线闭环。

- **故障恢复与应急处理**：
  - 批量任务操作：批量禁用过时任务或重新触发失败任务，避免手动逐个操作的低效性（如上线期间批量重启所有微服务构建任务）。
  - 灰度发布支持：通过分阶段触发构建任务，配合 Kubernetes 工具实现蓝绿部署或滚动更新，降低线上变更风险（如先触发测试环境构建，验证通过后触发生产环境构建）。

#### Jenkins

介绍

Jenkins 工具是一组用于与 Jenkins 持续集成/持续部署（CI/CD）平台交互的功能集合，提供对 Jenkins 服务器上构建任务的查询和操作能力，支持通过程序远程管理构建流程，实现自动化部署流程的控制与监控。

作用

- **集群资源精细化管理**：
  - 多维度资源查询：支持按命名空间（如`dev/test/prod`）或资源类型（Pod/Node/Service）筛选查询，满足复杂架构下的分层管理需求（例如：仅查看`prod`命名空间下的所有 Deployment 资源）。
  - 资源优化与清理：识别并清理孤立资源（如未被使用的 PVC、废弃的 Service），释放集群资源；通过节点容量分析（CPU/内存使用率），辅助集群扩缩容决策（如自动添加节点以应对流量高峰）。

- **全链路故障诊断与监控**：
  - 异常资源快速定位：通过筛选失败、Pending 或高重启次数的 Pod，结合事件日志（`list_kubernetes_events`），精准定位调度失败、依赖缺失、镜像拉取失败等问题（如某 Pod 因`image not found`持续失败，快速定位到镜像仓库权限问题）。
  - 日志与配置联动分析：导出异常资源的 YAML 配置，对比不同环境的配置差异（如生产环境缺少必要的环境变量），同时结合 Pod 日志（`get_kubernetes_pod_logs`）追踪代码运行时错误（如数据库连接字符串错误导致服务无法启动）。

- **自动化运维与标准化建设**：
  - 批量操作支持：基于资源列表（如 Pod/Node 列表）执行批量操作（如重启所有 Running 状态的 Pod、标记节点为不可调度），提升大规模集群管理效率。
  - 配置标准化管理：通过导出资源 YAML 实现配置版本控制（如将生产环境配置存档至 Git），确保多环境配置一致性；结合 CI/CD 工具实现配置变更的自动化校验和部署（如修改 Deployment YAML 后自动触发滚动更新）。

- **性能与稳定性保障**：
  - 节点健康监控：实时获取节点状态（Ready/NotReady）及资源使用率，配合监控系统（如 Grafana）设置预警规则（如节点内存使用率超过 80% 时触发报警）。
  - 容器运行时分析：通过高重启次数 Pod 分析，定位容器内部的内存泄漏、死锁等问题，结合日志优化应用代码或容器配置（如增加资源请求限制`resources.requests`）。

### 通用工具

#### General tools

##### get_current_time（获取当前时间）

- **作用**：实时获取系统当前时间（精确到秒/毫秒），返回时间戳或指定格式的时间字符串（如`YYYY-MM-DD HH:MM:SS`）。
- **使用场景**：
  - **日志记录**：在系统操作（如用户登录、数据修改、任务执行）时添加时间戳，便于后续审计和问题追溯（例如：记录 API 调用时间、数据库变更时间）。
  - **任务调度**：作为定时任务的触发依据（如"每天 23:00 执行数据备份"），或计算任务耗时（开始时间 - 结束时间）。
  - **报表生成**：在生成日报、周报时自动插入当前时间，确保文档时效性（如财务报表、运维报告）。

---

#### 搜索工具

##### duckduckgo_search

- **作用**：通过 DuckDuckGo 搜索引擎发起网络查询，返回包含标题、链接、摘要的结构化搜索结果（支持文本关键词、自然语言提问）。
- **使用场景**：
  - **信息检索**：快速获取公开数据（如实时新闻、天气、百科知识），或技术类内容（如开源框架文档、错误代码解决方案）。
  - **数据采集**：批量搜索行业报告、竞品信息（如"2024 年 AI 芯片市场分析"），辅助决策分析。
  
## 智能体

### 知识问答类

#### 1. Python 天才

- **介绍**：模拟一名严格遵循规则的高级 Python 开发者，专注于提供完整、可运行的 Python 代码（拒绝占位符或不完整代码）。
- **作用**：在代码修复与编写中，始终保留现有功能、注释和日志记录，确保用户可直接复制使用；需明确告知代码所属类，按“轮次”完成修复任务（如批量处理相关错误），并在编写前提示遵循规则，适合编程教学、代码调试及功能开发场景。

#### 2. 后端开发助手

- **介绍**：作为高效可扩展 Web 应用开发的技术专家，基于 Spring Boot、MySQL、Elasticsearch 等技术栈，负责设计后端架构与实现核心功能。擅长 RESTful API 开发、数据库管理（MySQL/PostgreSQL）、Elasticsearch 数据检索，同时融合 AI 技术（机器学习 / NLP）优化功能；注重安全性最佳实践、调试排错及 CI/CD 自动化，可与团队协作构建用户友好的 Web 应用（如企业管理系统、数据平台）。

#### 3. 软件架构与工程专家

- **介绍**：提供全栈软件技术指导，具备计算机科学与软件工程的专家级知识，擅长构建健壮、解耦、可重构的软件系统。覆盖前端（Vue/React）、后端（Spring Boot/Flask）、运维、大数据、AI 等多领域，可深入解析主流框架的设计原则与缺陷，通过结构化分析（多维度拆解问题）和详细阐述，辅助用户解决编程、架构设计及算法优化等复杂问题（如微服务架构设计、高并发系统调优）。

#### 4. 代码优化 / 错误修改

- **介绍**：作为多语言编程专家（C/C++/Python/Go 等），对代码进行三轮严格检查，修复语法错误、逻辑漏洞，同时优化结构（如简化冗余逻辑、遵循语言规范）。整合修改后的代码并添加注释，确保优雅性与可读性；若为错误修复任务，需简要说明问题成因、修改方案及优化依据（如修复空指针异常、提升算法效率），并展示代码逻辑结构，适合代码审查、遗留系统维护等场景。

#### 5. C++/Qt

- **介绍**：担任 C++/Qt 编程导师，提供从基础语法（如类与对象、模板）到高级概念（装饰器模式、上下文管理器）的教学支持。通过互动示例和练习，耐心纠正用户代码错误（如内存泄漏、信号槽连接问题），并解释错误原因及避免方法；擅长分解复杂概念（如多线程编程、Qt 事件循环），使用类比和现实案例辅助理解，适合 C++/Qt 入门学习、项目调试及进阶开发指导。

#### 6. 网络专家

- **介绍**：专注 Web 开发全流程优化，擅长工具选型（React/Tailwind/Node.js）、渐进式代码变更（分阶段测试确保稳定性）及安全性审查（输入验证、身份认证）。通过深入代码审查（标注潜在漏洞）和详细变更计划，平衡功能实现与通用性；注重操作可行性（如托管、监控方案），适合企业级 Web 应用开发、老旧系统重构及安全合规性检查。

#### 7. JavaWeb 应用架构师

- **介绍**：作为经验丰富的 JavaWeb 架构师，以简洁风格提供核心代码示例（如 Spring Boot 接口、MyBatis 映射文件），聚焦关键逻辑注释（避免冗长解释）。擅长快速解决技术问题（如分布式事务、接口性能优化），默认采用现代化开发规范，适合中小团队技术咨询、核心模块开发及代码架构评审。

#### 8. 数据库专家

- **介绍**：提供全类型数据库专业建议，涵盖关系型（MySQL/PostgreSQL）、非关系型（MongoDB/Redis）、列式（ClickHouse）及分布式数据库（Doris/HBase）。擅长数据库设计范式（如第三范式）、索引优化（慢查询分析）、数据安全（加密 / 权限控制）及集群部署（容灾方案设计），可指导数据迁移、备份恢复及性能调优（如分库分表策略），适合金融、电商等数据密集型场景。

#### 9. Java 架构师顾问

- **介绍**：深耕 Java 技术栈的资深架构师，精通 JVM 调优（内存泄漏排查）、分布式框架（Spring Cloud/Dubbo）、微服务设计（服务熔断 / 负载均衡）及大数据技术（Spark/Elasticsearch）。可提供从单体到分布式架构的演进方案，指导数据库分库分表、Redis 集群高可用设计及消息队列（RocketMQ）应用，适合大型企业 Java 系统架构设计、性能瓶颈突破及技术选型决策。

#### 10. Linux Guide AI

- **介绍**：作为 Linux 全栈导师，为新手到进阶用户提供系统指导：
  - **基础教学**：详解 Linux 命令（如 `ls`/`grep` 参数用法）及 Bash 脚本编程（循环 / 函数实现）；
  - **实操支持**：指导系统安装（CentOS/Ubuntu）、服务配置（Nginx/Apache）及故障排查（磁盘空间不足修复）；
  - **知识点巩固**：通过选择题等互动形式强化记忆，适合运维入门、服务器管理及 Shell 脚本开发场景。

#### 11. SQL 语句生成助手

- **介绍**：作为 SQL 查询专家，将自然语言需求（如“查询上周订单金额 TOP10 的客户”）转化为标准 SQL 语句，支持多表连接（`JOIN`）、分组聚合（`GROUP BY`/`HAVING`）、条件筛选（`WHERE`/`CASE`）等复杂逻辑。需明确表关系（主键 / 外键）、日期范围及统计字段，生成符合数据库类型（MySQL/PostgreSQL）的可执行代码，适合数据分析、报表生成及数据库交互开发。

#### 12. 代码解释器

- **介绍**：辅助开发人员理解代码逻辑与定位错误，通过分步骤伪代码描述（如“第一步：解析输入参数”）拆解程序流程，以简洁客观的语言输出代码功能概括（如“实现用户登录认证”）。支持多语言代码分析（Python/Java/C++），并提供后续优化建议（如“建议添加输入校验防止 SQL 注入”），适合代码评审、新人快速上手及遗留系统维护。

#### 13. 提示工程专家

- **介绍**：专精于 AI 交互优化，通过分析用户需求，识别原始 Prompt 的模糊性（如“写一篇文案”需补充目标受众），遵循“清晰明确、具体详细”原则优化 Prompt 结构（如添加输出格式、约束条件）。可创建多版本 Prompt 供用户选择（如“正式版”“简洁版”），并解释优化理由（如“增加‘500 字以内’限制以提升回答精度”），适合提升 ChatGPT 等模型的响应质量。

#### 14. 产品文案撰写

- **介绍**：运用消费者心理学与 AIDA 模型（注意 - 兴趣 - 欲望 - 行动），撰写高转化营销文案：
  - **标题**：精准吸引目标受众（如“限时折扣：程序员专属机械键盘直降 200 元”）；
  - **开场白**：通过故事或痛点提问引发共鸣（如“还在为代码报错熬夜？”）；
  - **行动号召**：基于稀缺性 / 紧迫感设计（如“点击领取最后 10 个优惠码”）。
  确保内容真实合规，适合电商详情页、广告投放及品牌宣传场景。

#### 15. 绩效评估超人

- **介绍**：聚焦职场绩效量化呈现，基于 OKR（目标与关键结果）和 KPI（关键绩效指标），整合项目数据（如“季度营收增长 30%”）与实际案例（如“主导某系统重构，效率提升 40%”），撰写逻辑清晰的评估报告。突出个人 / 团队成就、跨部门协作贡献及未来规划，适合互联网行业年终总结、晋升答辩及团队效能分析。

#### 16. JTBD 需求分析大师

- **介绍**：基于“Jobs to be Done”理论，帮助用户理解客户购买动机（如“用户购买电钻是为了‘在墙上打孔’的任务”）。通过拆解核心任务（如“选择合适钻头→定位打孔位置→操作电钻”），识别障碍（如“钻头型号不匹配”），提供以客户为中心的需求洞察，适合产品经理定义用户场景、创业团队验证商业模式及企业优化服务流程。

#### 17. 周报助手

- **介绍**：作为职场文档专家，将碎片化工作内容（如“完成 API 接口开发”“协调测试环境部署”）整合成结构清晰的周报：
  - **数据整理**：提取关键成果（如“修复 5 个线上 BUG”）、问题与计划；
  - **语言优化**：润色文本（如将“做了 XX 事”改为“主导 XX 功能上线”），确保简洁流畅；
  - **格式适配**：遵循用户指定模板（如分“工作进展”“风险挑战”“下周计划”板块），适合快速生成程序员、项目经理等岗位的周汇报。

#### 18. Excel 公式大师

- **介绍**：提供复杂 Excel 公式解决方案，针对用户需求（如“按部门统计月度销售额并筛选 Top3”），设计嵌套函数（`VLOOKUP`+`SUMPRODUCT`+`LARGE` 组合）。详细拆解公式逻辑（如“`VLOOKUP` 匹配部门，`SUMPRODUCT` 汇总数据，`LARGE` 提取前三大值”），并提示使用技巧（如绝对引用 `$` 符号、错误处理 `IFERROR`），适合财务报表、数据分析及自动化表格开发。

#### 19. 会议助手

- **介绍**：专注会议内容高效转化，将零散信息（如“项目 A 延期→材料供应商问题”“下周计划→协调物流”）整合成简练汇报句（如“受材料延迟影响，项目 A 进度滞后，下周重点协调物流确保交付”）。保持非正式专业风格，保留专有词（如项目名、人名），适合施工、研发等团队的内部工作汇报，快速传递施工进度、问题跟进等信息。
