# GEMINI.md

## Project Overview

This is a Python GUI application built with PyQt5. It serves as a "gateway tool" for interacting with devices over a serial port and communicating with an MQTT server. The application allows users to configure data sources, monitor real-time data, and manage MQTT connections.

**Key Technologies:**

*   Python
*   PyQt5
*   MQTT

## Building and Running

**1. Prerequisites:**

*   Python 3
*   PyQt5

**2. Installation:**

Install the required Python library:

```bash
pip install PyQt5
```

**3. Running the Application:**

To start the application, run the following command in your terminal:

```bash
python main.py
```

## Development Conventions

### UI Files

The user interface is designed using Qt Designer, and the `.ui` files are located in the root directory. These files are then converted to Python code.

*   `untitled.ui`: Main window UI.
*   `addsource.ui`: "Add data source" dialog UI.

To update the UI, you can edit the `.ui` files in Qt Designer and then regenerate the Python files using the `pyuic5` command:

```bash
pyuic5 -x untitled.ui -o window.py
pyuic5 -x addsource.ui -o config.py
```

### Resource Files

Image resources are managed using a Qt Resource Collection file (`.qrc`).

*   `res.qrc`: Lists the image files used in the application.

To update the resources, edit the `.qrc` file and then regenerate the Python file using the `pyrcc5` command:

```bash
pyrcc5 res.qrc -o res_rc.py
```

### Code Structure

*   `main.py`: The main entry point of the application.
*   `window.py`: Contains the main window's UI and logic (generated from `untitled.ui`).
*   `config.py`: Contains the "add data source" dialog's UI and logic (generated from `addsource.ui`).
*   `res_rc.py`: Contains the compiled resources (generated from `res.qrc`).

