# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-10-29

### Added

#### Core Features
- Initial release of WebChat library
- Session management with persistence
- State machine for chat flow control
- SSE (Server-Sent Events) handler with auto-reconnect
- Exponential backoff retry logic
- Event-based architecture

#### UI Components
- FloatingButton component with customizable position
- Chat component with message display
- Responsive design for mobile and desktop
- Light and dark theme support
- Typing indicators
- Message animations

#### Next.js Demo
- Full Next.js 14 setup with App Router
- SSE API endpoints for streaming
- Demo page with integration examples
- API route implementations

#### Build & Packaging
- TypeScript configuration for all packages
- Vite build configuration for UI
- Webpack configuration for UMD builds
- Monorepo setup with Turbo
- Source maps for debugging

#### Documentation
- Comprehensive README
- Integration guide with examples
- Contributing guidelines
- API documentation
- Architecture documentation

### Features

- 💬 Floating chat button with smooth animations
- 🔄 Real-time streaming with SSE
- 💾 Session persistence and history
- 🎨 Customizable themes
- 📱 Fully responsive design
- ⚙️ Robust state machine
- 🔌 Multiple integration options
- 🚀 Production-ready code

### Package Versions

- @webchat/core@1.0.0
- @webchat/ui@1.0.0
- @webchat/demo@1.0.0

## Planned Features (Roadmap)

### v1.1.0
- [ ] Voice message support
- [ ] Image upload from client
- [ ] Rich text editor
- [ ] Emoji picker
- [ ] Message reactions

### v1.2.0
- [ ] Multi-language support (i18n)
- [ ] Typing indicators
- [ ] Read receipts
- [ ] Message search
- [ ] Export chat history

### v2.0.0
- [ ] Mobile app (React Native)
- [ ] End-to-end encryption
- [ ] File sharing
- [ ] Video call integration
- [ ] Analytics dashboard

## Migration Guide

### From Rasa-web

If migrating from Rasa-web:

1. Update script URL to new WebChat CDN
2. Configuration options are mostly compatible
3. Event names may differ - check documentation
4. SSE format has changed - update backend

```javascript
// Old Rasa-web
window.WebChat.default({
  socketUrl: "http://rasa:5005",
});

// New WebChat
window.WebChat.default({
  socketUrl: "http://rasa:5005/webhooks/rest/webhook",
  enableSSE: true,
});
```

## Known Issues

- SSE connection may timeout after 30 seconds in some proxies
- localStorage has 5-10MB limit depending on browser
- Emoji support varies by browser

## Deprecation

No deprecated features in v1.0.0

## Security

- Sanitized HTML rendering
- CORS-compliant
- Session IDs are cryptographically random
- No credentials stored in localStorage

## Performance

- Initial bundle size: ~50KB (gzipped)
- No external dependencies required
- Minimal re-renders in React
- Efficient SSE handling

## Browser Support

| Browser | Version | Status |
|---------|---------|--------|
| Chrome  | 90+     | ✅     |
| Firefox | 88+     | ✅     |
| Safari  | 14+     | ✅     |
| Edge    | 90+     | ✅     |
| IE 11   | -       | ❌     |

## Supported Frameworks

- React 18+
- Next.js 14+
- Vue 3+
- Vanilla JS/TS
- Angular 14+

## Credits

Inspired by Rasa-web and other web chat libraries.

## License

MIT License - See LICENSE file for details
