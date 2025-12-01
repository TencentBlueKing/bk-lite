# Contributing to WebChat

Thank you for your interest in contributing to WebChat! This document provides guidelines and instructions for contributing.

## Code of Conduct

- Be respectful and inclusive
- Provide constructive feedback
- Report issues responsibly

## Getting Started

### Prerequisites

- Node.js >= 18.0.0
- npm or pnpm

### Setup Development Environment

```bash
git clone https://github.com/yourusername/webchat.git
cd webchat
npm install
npm run dev
```

## Development Workflow

### 1. Create Feature Branch

```bash
git checkout -b feature/your-feature-name
```

### 2. Make Changes

```bash
# Make your changes
# Ensure code follows project style guide
npm run lint
npm run format
```

### 3. Test Your Changes

```bash
npm run test
npm run build
```

### 4. Commit Changes

```bash
git add .
git commit -m "feat: description of your feature"
```

Use conventional commit messages:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation
- `style:` - Code style changes
- `refactor:` - Code refactoring
- `test:` - Test additions
- `chore:` - Maintenance tasks

### 5. Push and Create Pull Request

```bash
git push origin feature/your-feature-name
```

Create a PR on GitHub with a clear description.

## Code Standards

### TypeScript

- Use strict mode
- Add proper type annotations
- No `any` types (use `unknown` with type guards)

### React Components

- Use functional components with hooks
- Add PropTypes or TypeScript interfaces
- Include JSDoc comments for public APIs

Example:

```typescript
/**
 * Main chat component
 * @param props - Component props
 * @returns JSX element
 */
export const Chat: React.FC<ChatProps> = React.forwardRef((props, ref) => {
  // Implementation
});
```

### CSS

- Use CSS modules or BEM naming
- Ensure responsive design
- Support both light and dark themes

### Documentation

- Update README for new features
- Add JSDoc comments to functions
- Include usage examples

## Testing

```bash
# Run tests
npm run test

# Run tests with coverage
npm run test:coverage

# Run specific test file
npm run test -- sessionManager.test.ts
```

Write tests for:
- New features
- Bug fixes
- Edge cases

## Performance

- Profile changes with DevTools
- Avoid unnecessary re-renders (React)
- Optimize bundle size

## Security

- No hardcoded secrets
- Validate user input
- Sanitize HTML content
- Follow OWASP guidelines

## Documentation

Update docs for:
- New API endpoints
- Configuration options
- Breaking changes
- Examples and tutorials

## Commit Message Convention

```
type(scope): subject

body

footer
```

Example:

```
feat(sse): add auto-reconnect with exponential backoff

Add exponential backoff strategy to SSE reconnection.
Implements max retry attempts configuration.

Closes #123
```

## Pull Request Process

1. Update documentation
2. Add tests for changes
3. Ensure CI passes
4. Request review from maintainers
5. Address review feedback

## Release Process

1. Update version in package.json
2. Update CHANGELOG.md
3. Create git tag
4. Push to main branch
5. Publish to npm

## Reporting Issues

Include:
- Browser/Node.js version
- Reproduction steps
- Expected behavior
- Actual behavior
- Screenshots/logs

## Asking Questions

- Use GitHub Discussions for questions
- Check existing issues first
- Provide context and examples

## Project Structure

```
webchat/
├── packages/webchat-core/     # Core logic
├── packages/webchat-ui/       # React components
├── packages/webchat-demo/     # Demo app
├── build/                     # Build configs
└── tests/                     # Test files
```

## Branch Naming

- `feature/name` - New features
- `fix/name` - Bug fixes
- `docs/name` - Documentation
- `refactor/name` - Refactoring

## Help and Support

- GitHub Issues: For bug reports
- GitHub Discussions: For questions
- Slack: For real-time chat
- Email: support@example.com

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Acknowledgments

Thank you for contributing to making WebChat better!
