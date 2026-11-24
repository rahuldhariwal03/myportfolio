<?php
/**
 * Activation and deactivation.
 *
 * Activation is strictly non-destructive: it never touches posts, options or
 * theme files. It only registers the storage post type, grants the custom
 * capability to administrators, seeds content once (if empty) and records a
 * backup pointer so the very first state can always be restored.
 *
 * @package TrustUsBro\SiteManager
 */

defined( 'ABSPATH' ) || exit;

/**
 * Activator.
 */
class TUSB_Activator {

	/**
	 * Run on activation.
	 *
	 * @param bool $network_wide Multisite flag.
	 * @return void
	 */
	public static function activate( $network_wide = false ) {
		if ( $network_wide && is_multisite() ) {
			$sites = get_sites( array( 'fields' => 'ids', 'number' => 100 ) );
			foreach ( $sites as $site_id ) {
				switch_to_blog( (int) $site_id );
				self::activate_single();
				restore_current_blog();
			}
			return;
		}
		self::activate_single();
	}

	/**
	 * Single-site activation.
	 *
	 * @return void
	 */
	private static function activate_single() {
		// Ensure the plugin classes are available in the activation context.
		if ( ! class_exists( 'TUSB_Content_Store' ) ) {
			require_once TUSB_DIR . 'includes/class-content-store.php';
		}
		if ( ! class_exists( 'TUSB_Capabilities' ) ) {
			require_once TUSB_DIR . 'includes/class-capabilities.php';
		}
		if ( ! class_exists( 'TUSB_Backup' ) ) {
			require_once TUSB_DIR . 'includes/class-backup.php';
		}

		self::grant_caps();

		// The storage post type must be registered before we can write to it.
		$store = new TUSB_Content_Store();
		$store->register_post_type();

		// Seed starter content only if the site has no stored documents yet.
		if ( ! get_option( 'tusb_seeded' ) ) {
			self::seed( $store );
			update_option( 'tusb_seeded', time(), false );
		}

		// Record install metadata (never overwrite an existing value).
		if ( ! get_option( 'tusb_installed_at' ) ) {
			update_option( 'tusb_installed_at', time(), false );
		}
		update_option( 'tusb_version', TUSB_VERSION, false );

		// Snapshot the current state so the owner can always roll back.
		if ( class_exists( 'TUSB_Backup' ) && ! get_option( 'tusb_activation_backup' ) ) {
			$backup = new TUSB_Backup();
			$result = $backup->create( 'activation' );
			if ( ! is_wp_error( $result ) && isset( $result['id'] ) ) {
				update_option( 'tusb_activation_backup', $result['id'], false );
			}
		}

		flush_rewrite_rules( false );
	}

	/**
	 * Grant capabilities.
	 *
	 * @return void
	 */
	private static function grant_caps() {
		$role = get_role( 'administrator' );
		if ( $role ) {
			$role->add_cap( TUSB_Capabilities::MANAGE );
			$role->add_cap( TUSB_Capabilities::RESTORE );
		}
		$editor = get_role( 'editor' );
		if ( $editor ) {
			$editor->add_cap( TUSB_Capabilities::MANAGE );
		}
	}

	/**
	 * Seed starter content.
	 *
	 * The seeds contain neutral placeholders for a theme-agnostic install, and a
	 * live design-token-derived structure. They never overwrite existing content.
	 *
	 * @param TUSB_Content_Store $store Store.
	 * @return void
	 */
	private static function seed( $store ) {
		if ( ! class_exists( 'TUSB_Schema' ) ) {
			return;
		}
		require_once TUSB_DIR . 'includes/class-schema.php';
		require_once TUSB_DIR . 'includes/defaults.php';

		$seeds = tusb_seed_content();

		foreach ( $seeds as $doc_key => $payload ) {
			if ( $store->doc_post_id( $doc_key ) ) {
				continue;
			}
			$saved = $store->save_draft( $doc_key, $payload, array( 'label' => __( 'Starter content', 'trustusbro-site-manager' ) ) );
			if ( ! is_wp_error( $saved ) ) {
				$store->publish( $doc_key, null, array( 'label' => __( 'Starter content', 'trustusbro-site-manager' ) ) );
			}
		}
	}

	/**
	 * Deactivation: remove nothing, only tidy transient state.
	 *
	 * @param bool $network_wide Multisite flag.
	 * @return void
	 */
	public static function deactivate( $network_wide = false ) {
		// Content, options and revisions deliberately stay in place.
		delete_transient( 'tusb_flush_needed' );
		flush_rewrite_rules( false );
	}
}
