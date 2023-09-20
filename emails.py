from logging import Logger

from azure.communication.email import EmailClient


def send_email(
    connection_string,
    sender_email,
    recipient_email,
    subject,
    body,
    logger: Logger,
    html_content=None,
) -> dict:
    """
    Send an email using Azure Communication Services.

    Parameters:
    - connection_string (str): The connection string for Azure Communication Services.
    - sender_email (str): The sender's email address.
    - recipient_email (str): The recipient's email address.
    - subject (str): The subject of the email.
    - body (str): The plain text body content of the email.
    - html_content (str): The HTML content of the email. Optional.

    Returns:
    - dict: A dictionary containing the operation status and ID if successful.

    Raises:
    - RuntimeError: If the email sending process fails or times out.
    """
    email_client = EmailClient.from_connection_string(connection_string)

    message = {
        "content": {
            "subject": subject,
            "plainText": body,
            "html": html_content if html_content else f"<html><h1>{body}</h1></html>",
        },
        "recipients": {
            "to": [{"address": recipient_email, "displayName": "Customer Name"}]
        },
        "senderAddress": sender_email,
    }

    POLLER_WAIT_TIME = 10
    time_elapsed = 0

    try:
        poller = email_client.begin_send(message)

        while not poller.done():
            logger.debug(f"Email send poller status: {poller.status()}")
            poller.wait(POLLER_WAIT_TIME)
            time_elapsed += POLLER_WAIT_TIME

            if time_elapsed > 18 * POLLER_WAIT_TIME:
                raise RuntimeError("Polling timed out.")

        result = poller.result()
        if result["status"] == "Succeeded":
            logger.info(f"Successfully sent the email (operation id: {result['id']})")
            return {"status": "Succeeded", "operation_id": result["id"]}
        else:
            raise RuntimeError(result["error"])

    except Exception as ex:
        logger.exception(ex)
        raise RuntimeError(f"An error occurred: {str(ex)}")
