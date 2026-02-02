# Green API Helper

A desktop application for managing and examining Green API instances through secure API calls, featuring certificate-based authentication and Kibana integration for monitoring.

## Features

- **Instance Management**: Configure, monitor, and control Green API instances including state, settings, and lifecycle operations
- **Certificate Authentication**: Secure authentication using Windows certificate store for API access
- **Kibana Integration**: Direct access to ELK stack logs and monitoring for instance diagnostics
- **QR Code Management**: Generate and manage QR codes for instance setup and configuration
- **Message Journaling**: Examine incoming and outgoing message journals, chat history, and specific messages
- **Queue Management**: Monitor and manage message queues, webhooks, and status updates
- **Webhook Configuration**: Set up, modify, and clear webhook endpoints for real-time notifications
- **Status Monitoring**: Track message delivery statuses and statistics

## Installation

### Option 1: Pre-built Executable (Recommended)

Download the latest release from the [Releases](https://github.com/yourusername/greenapi-helper/releases) page:

1. Download `greenapi-helper.exe`
2. Run the executable (no installation required)
3. The app will guide you through certificate selection and authentication

### Option 2: From Source

```bash
# Clone the repository
git clone https://github.com/yourusername/greenapi-helper.git
cd greenapi-helper

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # On Windows

# Install dependencies
pip install -r requirements.txt

# Run the application
python -m app.main
```

## Requirements

- **Python**: 3.14+ (for source installation)
- **Operating System**: Windows 10/11 (required for certificate store access)
- **Certificates**: Valid client certificates in Windows Certificate Store
- **Network**: Access to Green API and Kibana endpoints

## Usage

1. **Launch the Application**
   - Run `greenapi-helper.exe` or `python -m app.main`

2. **Certificate Authentication**
   - Select your client certificate from the Windows store
   - The app will automatically authenticate with Kibana

3. **Instance Management**
   - Enter your Green API instance ID (10-digit number)
   - Use the Account tab to manage instance lifecycle (settings, reboot, logout)
   - Monitor instance state and configuration
   - Generate QR codes for WhatsApp API setup

4. **Examination and Monitoring**
   - **Journals Tab**: Review message history, incoming/outgoing journals, and specific chat interactions
   - **Queues Tab**: Monitor queued messages, webhook status, and manage queue operations
   - **Statuses Tab**: Track message delivery statuses and statistics

## Development

### Setup Development Environment

```bash
# Install development dependencies
pip install -r requirements.txt
pip install pytest flake8 black pyinstaller

# Run tests
pytest tests/

# Run linting
flake8 --max-line-length=120 --extend-ignore=E203,W503 app/ greenapi/ ui/

# Format code
black --line-length 120 app/ greenapi/ ui/
```

### Project Structure

```
greenapi-helper/
├── app/                    # Main application code
│   ├── main.py            # Entry point and UI
│   ├── resources.py       # Resource management
│   └── version.py         # Version information
├── greenapi/              # API client modules
│   ├── client.py          # HTTP client and API calls
│   ├── credentials.py     # Certificate management
│   ├── elk_auth.py        # Kibana authentication
│   └── api_url_resolver.py # URL resolution logic
├── ui/                    # User interface components
│   └── dialogs/           # Dialog windows for forms and settings
├── tests/                 # Test suite
└── .github/workflows/     # CI/CD configuration
```

### Building from Source

```bash
# Create executable
pyinstaller --onefile --windowed --name greenapi-helper app/main.py

# The executable will be in the dist/ folder
```

## CI/CD

This project uses GitHub Actions for automated quality assurance:

- **Automated Testing**: pytest runs on every push and pull request
- **Code Quality**: flake8 linting ensures consistent code style
- **Automated Builds**: PyInstaller creates Windows executables
- **Releases**: Automatic versioned releases with downloadable binaries

### Workflow Triggers

- **Push to main/master**: Full pipeline (test → lint → build → release)
- **Pull Requests**: Test and lint validation
- **Manual**: Can be triggered manually for testing

## Configuration

### Environment Variables

Create a `.env.local` file in the project root:

```env
# Kibana Configuration (required for authentication)
KIBANA_URL=https://your-kibana-instance.com
KIBANA_USER=your-username

# Optional: Override default API URL
# GREEN_API_BASE_URL=https://api.green-api.com
```

### Certificate Requirements

- Certificates must be installed in Windows Certificate Store (Personal/My)
- Private key must be accessible
- Certificate should be valid and not expired
- Supported: PKCS#12 (.pfx/.p12) and individual cert/key files

## Troubleshooting

### Common Issues

**Certificate Not Found**
- Ensure certificates are in Windows Certificate Store
- Check certificate validity dates
- Verify private key accessibility

**Authentication Failed**
- Check Kibana URL and credentials in `.env.local`
- Verify network connectivity
- Check certificate trust settings

**API Connection Issues**
- Verify instance ID format (10 digits)
- Check API token validity
- Ensure Green API service availability

### Debug Mode

Run with debug logging:
```bash
python -m app.main --debug
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass and linting is clean
6. Submit a pull request

## License

[I potentially need to add some license information here]

## Support

For issues and questions:
- Create an issue on GitHub
- Check the troubleshooting section
- Review the CI/CD logs for build issues

---

## Safety notes

- The **Reboot Instance** and destructive actions prompt for confirmation.
- Do not share `.env.local`, cookies, or certificate files.
- Each user should use their own credentials.

---

## Troubleshooting

### Buttons do nothing

- Ensure your certificate is present in Windows Certificate Store (Current User → Personal)
- Confirm the certificate has a private key
- Verify Kibana access and credentials

### Certificate errors

- Verify the certificate is valid and not expired
- Re-import with “Mark this key as exportable” if required

### “apiToken not found”

- The instance may be inactive
- Check Kibana access and time range settings

---

## Support / improvements

Contact the maintainer for new endpoints, UI changes, or output formatting adjustments.
