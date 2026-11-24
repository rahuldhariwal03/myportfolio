<?php
/**
 * Built-in contact form fallback.
 *
 * Used only when no form plugin shortcode is configured. Handles a nonce,
 * a honeypot, simple throttling and sanitisation, then emails the configured
 * recipient through wp_mail().
 *
 * @package TrustUsBro\SiteManager
 */

defined( 'ABSPATH' ) || exit;

/**
 * Forms.
 */
class TUSB_Forms {

	/**
	 * Register hooks.
	 *
	 * @return void
	 */
	public function hooks() {
		add_action( 'admin_post_nopriv_tusb_contact', array( $this, 'handle' ) );
		add_action( 'admin_post_tusb_contact', array( $this, 'handle' ) );
	}

	/**
	 * Process a submission.
	 *
	 * @return void
	 */
	public function handle() {
		$redirect = isset( $_POST['tusb_redirect'] ) ? esc_url_raw( wp_unslash( $_POST['tusb_redirect'] ) ) : home_url( '/' );
		$redirect = wp_validate_redirect( $redirect, home_url( '/' ) );

		if ( ! isset( $_POST['tusb_contact_nonce'] ) || ! wp_verify_nonce( sanitize_text_field( wp_unslash( $_POST['tusb_contact_nonce'] ) ), 'tusb_contact' ) ) {
			wp_safe_redirect( add_query_arg( 'tusb_sent', 'error', $redirect ) );
			exit;
		}

		// Honeypot.
		if ( ! empty( $_POST['tusb_website'] ) ) {
			wp_safe_redirect( add_query_arg( 'tusb_sent', 'ok', $redirect ) );
			exit;
		}

		$name    = isset( $_POST['tusb_name'] ) ? sanitize_text_field( wp_unslash( $_POST['tusb_name'] ) ) : '';
		$email   = isset( $_POST['tusb_email'] ) ? sanitize_email( wp_unslash( $_POST['tusb_email'] ) ) : '';
		$phone   = isset( $_POST['tusb_phone'] ) ? sanitize_text_field( wp_unslash( $_POST['tusb_phone'] ) ) : '';
		$message = isset( $_POST['tusb_message'] ) ? sanitize_textarea_field( wp_unslash( $_POST['tusb_message'] ) ) : '';

		if ( '' === $name || ! is_email( $email ) || '' === $message ) {
			wp_safe_redirect( add_query_arg( 'tusb_sent', 'error', $redirect ) );
			exit;
		}

		// Light throttling: one submission per minute per IP.
		$ip  = isset( $_SERVER['REMOTE_ADDR'] ) ? sanitize_text_field( wp_unslash( $_SERVER['REMOTE_ADDR'] ) ) : '';
		$key = 'tusb_form_' . md5( $ip );
		if ( get_transient( $key ) ) {
			wp_safe_redirect( add_query_arg( 'tusb_sent', 'error', $redirect ) );
			exit;
		}
		set_transient( $key, 1, MINUTE_IN_SECONDS );

		$store   = tusb()->module( 'store' );
		$contact = $store ? $store->resolve( 'contact', 'published' ) : array();
		$to      = ! empty( $contact['recipient'] ) ? $contact['recipient'] : get_option( 'admin_email' );

		$subject = sprintf(
			/* translators: %s: site name. */
			__( 'New website enquiry from %s', 'trustusbro-site-manager' ),
			get_bloginfo( 'name' )
		);

		$body  = sprintf( "%s\n\n%s\n\n%s\n\n---\n%s\n%s\n%s\n", $name, $email, $message, __( 'Sent from the website contact form.', 'trustusbro-site-manager' ), $phone, home_url( '/' ) );
		$sent  = wp_mail( $to, $subject, $body, array( 'Reply-To: ' . $name . ' <' . $email . '>' ) );

		do_action( 'tusb_contact_submitted', $sent, compact( 'name', 'email', 'phone', 'message' ) );

		wp_safe_redirect( add_query_arg( 'tusb_sent', $sent ? 'ok' : 'error', $redirect ) );
		exit;
	}
}
