# Third-party components

The project source in this repository has its own [MIT license](LICENSE). It does not override licenses of separately downloaded software, model weights, container images or their dependencies. The demo source ZIP does not bundle Switch, Qwen weights, llama.cpp or the container images.

- **Switch**: setup checks out commit `b09e7ce4cb6abfad3783d3d7d75f45a09608dc45` and uses the upstream local Compose stack. [License at that commit](https://github.com/sandbox-quantum/switch/blob/b09e7ce4cb6abfad3783d3d7d75f45a09608dc45/LICENSE): Apache 2.0 **as limited by the modified Commons Clause**, which restricts selling the software or derivatives as described there. Do not describe that license as unqualified Apache 2.0.
- **Qwen3 0.6B**: the script downloads Unsloth's Q4_K_M GGUF from [unsloth/Qwen3-0.6B-GGUF](https://huggingface.co/unsloth/Qwen3-0.6B-GGUF). [Qwen's model license](https://huggingface.co/Qwen/Qwen3-0.6B-GGUF/blob/main/LICENSE) is Apache 2.0; verify the actual distribution terms before redistribution.
- **llama.cpp**: b11669 release binary downloaded from [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp/releases/tag/b11669); see its [license](https://github.com/ggml-org/llama.cpp/blob/master/LICENSE) and bundled dependency notices.
- **Mattermost**, PostgreSQL and other Docker images are pulled via the upstream Switch Compose stack. Review each image's terms and notices separately.
- **Python requests**, used for HTTP, is installed from PyPI; see [requests](https://github.com/psf/requests) and its transitive dependencies' licenses.
- The synthetic demo is based on the public [octocat/Hello-World](https://github.com/octocat/Hello-World) repository; its local modifications are synthetic and are not pushed.

No third-party component is represented as endorsed by its maintainers. This notice is not legal advice.
