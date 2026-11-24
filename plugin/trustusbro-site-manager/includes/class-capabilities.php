<?php
/**
 * Capability-based permissions.
 *
 * @package TrustUsBro\SiteManager
 */

defined( 'ABSPATH' ) || exit;

/**
 * Capabilities.
 */
class TUSB_Capabilities {

	/**
	 * Custom capability granted to editors of the site.
	 */
	const MANAGE = 'tusb_manage_site';

	/**
	 * Capability for restoring backups / importing content.
	 */
	const RESTORE = 'tusb_restore_site';

	/**
	 * Register hooks.
	 *
	 * @return void
	 */
	public function hooks() {
		add_filter( 'map_meta_cap', array( $this, 'map_meta_cap' ), 10, 4 );
	}

	/**
	 * Translate our custom caps for administrators who have not been granted
	 * them explicitly (e.g. installs that skipped activation).
	 *
	 * @param array  $caps Required caps.
	 * @param string $cap Cap being checked.
	 * @param int    $user_id User ID.
	 * @param array  $args Args.
	 * @return array
	 */
	public function map_meta_cap( $caps, $cap, $user_id, $args ) {
		if ( self::MANAGE !== $cap && self::RESTORE !== $cap ) {
			return $caps;
		}

		// Never call user_can()/current_user_can() from here: that re-enters this
		// filter and recurses. Inspect the role object instead, which is safe.
		$user = get_userdata( $user_id );
		if ( ! $user || ! in_array( 'administrator', (array) $user->roles, true ) ) {
			return $caps;
		}

		$role = get_role( 'administrator' );
		if ( ! $role || ! $role->has_cap( $cap ) ) {
			// Activation grants the cap; if it was revoked or skipped, fall back to
			// the built-in administrator capability so the site stays manageable.
			return array( 'manage_options' );
		}

		return $caps;
	}

	/**
	 * Can the current user manage site content?
	 *
	 * @return bool
	 */
	public static function can_manage() {
		return current_user_can( self::MANAGE ) || current_user_can( 'manage_options' );
	}

	/**
	 * Can the current user restore backups?
	 *
	 * @return bool
	 */
	public static function can_restore() {
		return current_user_can( self::RESTORE ) || current_user_can( 'manage_options' );
	}
}
