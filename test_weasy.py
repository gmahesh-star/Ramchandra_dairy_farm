try:
    from weasyprint import HTML
    print("WeasyPrint imported successfully.")
except Exception as e:
    print(f"Error importing WeasyPrint: {e}")
