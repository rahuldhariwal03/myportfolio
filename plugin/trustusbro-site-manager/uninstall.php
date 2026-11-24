<?php
/**
 * Uninstall routine.
 *
 * Deleting a plugin must never destroy a site owner's content, so this file does
 * nothing at all unless the owner explicitly opts in by setting the
 * `tusb_purge_on_uninstall` option to a truthy value (for example
 * `wp option update tusb_purge_on_uninstall 1`). Deactivation, deletion and
 * uninstall all leave content, revisions, settings and backup files untouched.
 *
 * @package TrustUsBro\SiteManager
 */

defined( 'WP_UNINSTALL_PLUGIN' ) || exit;

if ( ! get_option( 'tusb_purge_on_uninstall' ) ) {
	return;
}

/**
 * Remove one site's data.
 *
 * @return void
 */
function tusb_uninstall_site_data() {
	global $wpdb;

	// 1. Documents and their revisions live in the tusb_content post type.
	$post_ids = $wpdb->get_col( // phpcs:ignore WordPress.DB.DirectDatabaseQuery
		$wpdb->prepare( "SELECT ID FROM {$wpdb->posts} WHERE post_type = %s", 'tusb_content' )
	);
	foreach ( array_map( 'intval', $post_ids ) as $post_id ) {
		wp_delete_post( $post_id, true );
	}

	// 2. Options and transients created by the plugin.
	$options = array(
		'tusb_settings',
		'tusb_seeded',
		'tusb_version',
		'tusb_installed_at',
		'tusb_activation_backup',
		'tusb_backups',
		'tusb_last_backup',
		'tusb_purge_on_uninstall',
	);
	foreach ( $options as $option ) {
		delete_option( $option );
	}
	delete_transient( 'tusb_flush_needed' );
	wp_clear_scheduled_hook( 'tusb_daily_backup' );

	// 3. Capabilities granted on activation.
	foreach ( array( 'administrator', 'editor' ) as $role_name ) {
		$role = get_role( $role_name );
		if ( $role ) {
			$role->remove_cap( 'tusb_manage_site' );
			$role->remove_cap( 'tusb_restore_site' );
		}
	}

	// 4. Backup files, only inside the plugin's own directory.
	$uploads = wp_upload_dir();
	$dir     = trailingslashit( $uploads['basedir'] ) . 'trustusbro-backups/';
	if ( is_dir( $dir ) ) {
		$files = glob( $dir . '*.json' );
		if ( is_array( $files ) ) {
			foreach ( $files as $file ) {
				if ( is_file( $file ) ) {
					wp_delete_file( $file );
				}
			}
		}
	}
}

if ( is_multisite() ) {
	$site_ids = get_sites( array( 'fields' => 'ids', 'number' => 0 ) );
	foreach ( $site_ids as $site_id ) {
		switch_to_blog( (int) $site_id );
		if ( get_option( 'tusb_purge_on_uninstall' ) ) {
			tusb_uninstall_site_data();
		}
		restore_current_blog();
	}
} else {
	tusb_uninstall_site_data();
}
