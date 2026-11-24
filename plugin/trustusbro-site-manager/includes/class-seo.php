<?php
/**
 * SEO module.
 *
 * A deliberately conservative meta layer. It never fights another SEO plugin:
 * if Yoast, Rank Math, AIOSEO, SEOPress or The SEO Framework is active, this
 * module only stores defaults and registers compatibility hooks with them
 * instead of printing duplicate tags.
 *
 * @package TrustUsBro\SiteManager
 */

defined( 'ABSPATH' ) || exit;

/**
 * SEO.
 */
class TUSB_SEO {

	/**
	 * Register hooks.
	 *
	 * @return void
	 */
	public function hooks() {
		add_action( 'init', array( $this, 'maybe_register_meta' ) );
		add_filter( 'document_title_separator', array( $this, 'title_separator' ), 20 );
		add_filter( 'document_title_parts', array( $this, 'title_parts' ), 20 );
		add_action( 'wp_head', array( $this, 'output_meta' ), 1 );
		add_filter( 'robots_txt', array( $this, 'robots_txt' ), 20, 2 );
		add_filter( 'wp_robots', array( $this, 'wp_robots' ), 20 );
		add_action( 'admin_init', array( $this, 'register_seo_fields' ) );
		add_filter( 'rank_math/frontend/title', array( $this, 'rank_math_title' ) );
		add_filter( 'rank_math/frontend/description', array( $this, 'rank_math_description' ) );
	}

	/**
	 * Stored SEO defaults.
	 *
	 * @return array
	 */
	public static function defaults() {
		$store = tusb()->module( 'store' );
		$data  = $store ? $store->resolve( 'seo', 'published' ) : array();
		return is_array( $data ) ? $data : array();
	}

	/**
	 * Should this module print its own meta tags?
	 *
	 * @return bool
	 */
	public static function prints_meta() {
		return ! TUSB_Compat::other_seo_active();
	}

	/**
	 * Register post meta so SEO values are available over the REST API and editable
	 * from the block editor sidebar.
	 *
	 * @return void
	 */
	public function maybe_register_meta() {
		$fields = array(
			'_tusb_seo_title'       => 'string',
			'_tusb_seo_description' => 'string',
			'_tusb_seo_noindex'     => 'boolean',
			'_tusb_seo_canonical'   => 'string',
			'_tusb_seo_og_image'    => 'integer',
		);
		foreach ( $fields as $key => $type ) {
			register_post_meta(
				'',
				$key,
				array(
					'type'              => $type,
					'single'            => true,
					'show_in_rest'      => true,
					'sanitize_callback' => 'boolean' === $type
						? array( 'TUSB_Sanitizer', 'to_bool' )
						: ( '_tusb_seo_og_image' === $key ? array( 'TUSB_Sanitizer', 'image_id' ) : 'sanitize_text_field' ),
					'auth_callback'     => static function () {
						return current_user_can( 'edit_posts' );
					},
				)
			);
		}
	}

	/**
	 * Add SEO fields to posts/pages in the block editor (Gutenberg sidebar).
	 *
	 * @return void
	 */
	public function register_seo_fields() {
		if ( ! function_exists( 'register_post_meta' ) ) {
			return;
		}
		add_action( 'enqueue_block_editor_assets', array( $this, 'editor_assets' ) );
	}

	/**
	 * Enqueue the small SEO panel for the block editor.
	 *
	 * @return void
	 */
	public function editor_assets() {
		wp_enqueue_script(
			'tusb-editor-seo',
			TUSB_URL . 'assets/js/editor-seo.js',
			array( 'wp-plugins', 'wp-edit-post', 'wp-element', 'wp-components', 'wp-data', 'wp-i18n' ),
			TUSB_VERSION,
			true
		);
	}

	/**
	 * Resolve the effective title for the current request.
	 *
	 * @return string
	 */
	public function current_title() {
		if ( is_singular() ) {
			$custom = get_post_meta( get_queried_object_id(), '_tusb_seo_title', true );
			if ( $custom ) {
				return (string) $custom;
			}
			return get_the_title( get_queried_object_id() );
		}
		if ( is_home() || is_front_page() ) {
			return get_bloginfo( 'name' ) . ' — ' . get_bloginfo( 'description' );
		}
		if ( is_archive() ) {
			return wp_strip_all_tags( get_the_archive_title() );
		}
		if ( is_search() ) {
			/* translators: %s: search query. */
			return sprintf( __( 'Search results for %s', 'trustusbro-site-manager' ), get_search_query() );
		}
		return get_bloginfo( 'name' );
	}

	/**
	 * Resolve the meta description.
	 *
	 * @return string
	 */
	public function current_description() {
		if ( is_singular() ) {
			$custom = get_post_meta( get_queried_object_id(), '_tusb_seo_description', true );
			if ( $custom ) {
				return (string) $custom;
			}
			$post = get_post( get_queried_object_id() );
			if ( $post ) {
				$excerpt = has_excerpt( $post ) ? get_the_excerpt( $post ) : wp_strip_all_tags( strip_shortcodes( $post->post_content ) );
				if ( $excerpt ) {
					return wp_trim_words( $excerpt, 30, '…' );
				}
			}
		}
		$defaults = self::defaults();
		if ( ! empty( $defaults['meta_description'] ) ) {
			return $defaults['meta_description'];
		}
		return get_bloginfo( 'description' );
	}

	/**
	 * Title separator.
	 *
	 * @param string $sep Separator.
	 * @return string
	 */
	public function title_separator( $sep ) {
		if ( ! self::prints_meta() ) {
			return $sep;
		}
		return '|';
	}

	/**
	 * Append the configured suffix to titles.
	 *
	 * @param array $parts Title parts.
	 * @return array
	 */
	public function title_parts( $parts ) {
		if ( ! self::prints_meta() || is_admin() ) {
			return $parts;
		}
		$defaults = self::defaults();
		$suffix   = ! empty( $defaults['title_suffix'] ) ? $defaults['title_suffix'] : '';
		$suffix   = str_replace( '{site}', get_bloginfo( 'name' ), $suffix );
		if ( $suffix ) {
			$parts['site'] = trim( $suffix, ' |—-' );
		}
		return $parts;
	}

	/**
	 * Rank Math filters: real integration instead of duplicated tags.
	 *
	 * @param string $title Title.
	 * @return string
	 */
	public function rank_math_title( $title ) {
		if ( is_singular() ) {
			$custom = get_post_meta( get_queried_object_id(), '_tusb_seo_title', true );
			if ( $custom ) {
				return $custom;
			}
		}
		return $title;
	}

	/**
	 * Rank Math description filter.
	 *
	 * @param string $description Description.
	 * @return string
	 */
	public function rank_math_description( $description ) {
		if ( is_singular() ) {
			$custom = get_post_meta( get_queried_object_id(), '_tusb_seo_description', true );
			if ( $custom ) {
				return $custom;
			}
		}
		return $description;
	}

	/**
	 * Output canonical, Open Graph, Twitter and JSON-LD schema when no other SEO
	 * plugin is handling it.
	 *
	 * @return void
	 */
	public function output_meta() {
		if ( ! self::prints_meta() ) {
			return;
		}

		$defaults    = self::defaults();
		$title       = $this->current_title();
		$description = $this->current_description();
		$url         = $this->current_url();
		$image_id    = 0;

		if ( is_singular() ) {
			$image_id = (int) get_post_meta( get_queried_object_id(), '_tusb_seo_og_image', true );
			if ( ! $image_id && has_post_thumbnail( get_queried_object_id() ) ) {
				$image_id = (int) get_post_thumbnail_id( get_queried_object_id() );
			}
		}
		if ( ! $image_id && ! empty( $defaults['og_image'] ) ) {
			$image_id = (int) $defaults['og_image'];
		}
		$image_url = $image_id ? wp_get_attachment_image_url( $image_id, 'large' ) : '';

		$canonical = is_singular() ? (string) get_post_meta( get_queried_object_id(), '_tusb_seo_canonical', true ) : '';
		if ( ! $canonical ) {
			$canonical = $url;
		}

		echo "\n<!-- TrustUsBro Site Manager SEO -->\n";
		printf( '<link rel="canonical" href="%s" />' . "\n", esc_url( $canonical ) );
		if ( $description ) {
			printf( '<meta name="description" content="%s" />' . "\n", esc_attr( $description ) );
		}
		printf( '<meta property="og:type" content="%s" />' . "\n", is_singular( 'post' ) ? 'article' : 'website' );
		printf( '<meta property="og:site_name" content="%s" />' . "\n", esc_attr( get_bloginfo( 'name' ) ) );
		printf( '<meta property="og:title" content="%s" />' . "\n", esc_attr( $title ) );
		if ( $description ) {
			printf( '<meta property="og:description" content="%s" />' . "\n", esc_attr( $description ) );
		}
		printf( '<meta property="og:url" content="%s" />' . "\n", esc_url( $url ) );
		if ( $image_url ) {
			printf( '<meta property="og:image" content="%s" />' . "\n", esc_url( $image_url ) );
		}
		printf( '<meta name="twitter:card" content="%s" />' . "\n", $image_url ? 'summary_large_image' : 'summary' );
		if ( ! empty( $defaults['twitter_handle'] ) ) {
			printf( '<meta name="twitter:site" content="@%s" />' . "\n", esc_attr( ltrim( $defaults['twitter_handle'], '@' ) ) );
		}
		printf( '<meta name="twitter:title" content="%s" />' . "\n", esc_attr( $title ) );
		if ( $description ) {
			printf( '<meta name="twitter:description" content="%s" />' . "\n", esc_attr( $description ) );
		}
		if ( $image_url ) {
			printf( '<meta name="twitter:image" content="%s" />' . "\n", esc_url( $image_url ) );
		}

		$this->output_schema( $defaults, $title, $description, $url, $image_url );
		echo "<!-- /TrustUsBro Site Manager SEO -->\n\n";
	}

	/**
	 * JSON-LD schema: Organization on the front page, Article on posts, FAQ on
	 * pages that contain a Site Manager FAQ section.
	 *
	 * @param array  $defaults Defaults.
	 * @param string $title Title.
	 * @param string $description Description.
	 * @param string $url URL.
	 * @param string $image_url Image URL.
	 * @return void
	 */
	protected function output_schema( $defaults, $title, $description, $url, $image_url ) {
		$graph = array();

		$org_name = ! empty( $defaults['organization'] ) ? $defaults['organization'] : get_bloginfo( 'name' );
		$org      = array(
			'@type' => 'Organization',
			'@id'   => home_url( '/#organization' ),
			'name'  => $org_name,
			'url'   => home_url( '/' ),
		);
		if ( ! empty( $defaults['logo'] ) ) {
			$logo = wp_get_attachment_image_url( (int) $defaults['logo'], 'full' );
			if ( $logo ) {
				$org['logo'] = array(
					'@type' => 'ImageObject',
					'url'   => $logo,
				);
			}
		}
		$same_as = array();
		foreach ( (array) tusb_arr( $defaults, 'schema_types', array() ) as $row ) {
			if ( ! empty( $row['url'] ) ) {
				$same_as[] = $row['url'];
			}
		}
		$contact = tusb()->module( 'store' ) ? tusb()->module( 'store' )->resolve( 'contact', 'published' ) : array();
		if ( ! empty( $contact['social'] ) ) {
			foreach ( $contact['social'] as $link ) {
				if ( ! empty( $link['url'] ) ) {
					$same_as[] = $link['url'];
				}
			}
		}
		$same_as = array_values( array_unique( array_filter( $same_as ) ) );
		if ( $same_as ) {
			$org['sameAs'] = $same_as;
		}
		if ( ! empty( $contact['email'] ) || ! empty( $contact['phone'] ) ) {
			$org['contactPoint'] = array(
				'@type'             => 'ContactPoint',
				'contactType'       => 'customer service',
				'email'             => isset( $contact['email'] ) ? $contact['email'] : '',
				'telephone'         => isset( $contact['phone'] ) ? $contact['phone'] : '',
			);
		}
		$graph[] = $org;

		$graph[] = array(
			'@type'           => 'WebSite',
			'@id'             => home_url( '/#website' ),
			'url'             => home_url( '/' ),
			'name'            => get_bloginfo( 'name' ),
			'publisher'       => array( '@id' => home_url( '/#organization' ) ),
			'inLanguage'      => get_bloginfo( 'language' ),
		);

		$graph[] = array(
			'@type'       => 'WebPage',
			'@id'         => $url . '#webpage',
			'url'         => $url,
			'name'        => $title,
			'description' => $description,
			'isPartOf'    => array( '@id' => home_url( '/#website' ) ),
		);

		if ( is_singular( 'post' ) ) {
			$post_id = get_queried_object_id();
			$article = array(
				'@type'            => 'Article',
				'@id'              => $url . '#article',
				'headline'         => $title,
				'description'      => $description,
				'datePublished'    => get_the_date( 'c', $post_id ),
				'dateModified'     => get_the_modified_date( 'c', $post_id ),
				'author'           => array(
					'@type' => 'Person',
					'name'  => get_the_author_meta( 'display_name', (int) get_post_field( 'post_author', $post_id ) ),
				),
				'publisher'        => array( '@id' => home_url( '/#organization' ) ),
				'mainEntityOfPage' => array( '@id' => $url . '#webpage' ),
			);
			if ( $image_url ) {
				$article['image'] = $image_url;
			}
			$graph[] = $article;
		}

		$faq_items = $this->faq_for_current_page();
		if ( $faq_items ) {
			$entities = array();
			foreach ( $faq_items as $item ) {
				if ( empty( $item['question'] ) || empty( $item['answer'] ) ) {
					continue;
				}
				$entities[] = array(
					'@type'          => 'Question',
					'name'           => wp_strip_all_tags( $item['question'] ),
					'acceptedAnswer' => array(
						'@type' => 'Answer',
						'text'  => wp_strip_all_tags( $item['answer'] ),
					),
				);
			}
			if ( $entities ) {
				$graph[] = array(
					'@type'      => 'FAQPage',
					'@id'        => $url . '#faq',
					'mainEntity' => $entities,
				);
			}
		}

		$schema = array(
			'@context' => 'https://schema.org',
			'@graph'   => $graph,
		);

		echo '<script type="application/ld+json">' . wp_json_encode( $schema, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE ) . '</script>' . "\n"; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- JSON-LD.
	}

	/**
	 * Which editable document backs the page being viewed, if any.
	 *
	 * @return string Empty string when the page is not Site Manager managed.
	 */
	protected function page_doc_key() {
		if ( is_front_page() ) {
			return 'home';
		}
		if ( is_page() ) {
			$slug = (string) get_post_field( 'post_name', get_queried_object_id() );
			$map  = array_keys( tusb_page_docs() );
			if ( in_array( $slug, $map, true ) ) {
				return $slug;
			}
		}
		return '';
	}

	/**
	 * FAQ items relevant to the current request.
	 *
	 * @return array
	 */
	protected function faq_for_current_page() {
		$store = tusb()->module( 'store' );
		if ( ! $store ) {
			return array();
		}
		if ( ! is_front_page() && ! is_page() ) {
			return array();
		}

		$items = array();

		// 1. Items written straight into the FAQ collection.
		$data = $store->resolve( 'faq', 'published' );
		if ( ! empty( $data['items'] ) && is_array( $data['items'] ) ) {
			foreach ( $data['items'] as $item ) {
				$items[] = array(
					'question' => isset( $item['question'] ) ? $item['question'] : '',
					'answer'   => isset( $item['answer'] ) ? $item['answer'] : '',
					'visible'  => isset( $item['visible'] ) ? (bool) $item['visible'] : true,
				);
			}
		}

		// 2. Questions typed into an FAQ *section* of the page being viewed, so the
		//    structured data always matches what a visitor can actually see.
		$doc_key = $this->page_doc_key();
		if ( $doc_key ) {
			$page = $store->resolve( $doc_key, 'published' );
			if ( ! empty( $page['sections'] ) && is_array( $page['sections'] ) ) {
				foreach ( $page['sections'] as $section ) {
					if ( ! isset( $section['type'] ) || 'faq' !== $section['type'] ) {
						continue;
					}
					if ( isset( $section['enabled'] ) && ! $section['enabled'] ) {
						continue;
					}
					if ( empty( $section['items'] ) || ! is_array( $section['items'] ) ) {
						continue;
					}
					foreach ( $section['items'] as $item ) {
						$items[] = array(
							'question' => isset( $item['question'] ) ? $item['question'] : '',
							'answer'   => isset( $item['answer'] ) ? $item['answer'] : '',
							'visible'  => ! isset( $item['visible'] ) || (bool) $item['visible'],
						);
					}
				}
			}
		}

		$items = array_filter( $items, static function ( $item ) {
			return ! empty( $item['visible'] ) && '' !== trim( wp_strip_all_tags( (string) $item['question'] ) ) && '' !== trim( wp_strip_all_tags( (string) $item['answer'] ) );
		} );

		// Guard against the same question appearing in both places.
		$seen = array();
		$out  = array();
		foreach ( $items as $item ) {
			$hash = md5( strtolower( trim( wp_strip_all_tags( $item['question'] ) ) ) );
			if ( isset( $seen[ $hash ] ) ) {
				continue;
			}
			$seen[ $hash ] = true;
			$out[]         = $item;
		}

		return array_slice( array_values( $out ), 0, 10 );
	}

	/**
	 * Current canonical URL.
	 *
	 * @return string
	 */
	protected function current_url() {
		if ( is_singular() ) {
			$permalink = get_permalink();
			return $permalink ? $permalink : home_url( '/' );
		}
		if ( is_front_page() ) {
			return home_url( '/' );
		}
		global $wp;
		$path = isset( $wp->request ) ? $wp->request : '';
		return home_url( user_trailingslashit( $path ) );
	}

	/**
	 * Robots directives.
	 *
	 * @param array $robots Robots directives.
	 * @return array
	 */
	public function wp_robots( $robots ) {
		$defaults = self::defaults();
		if ( ! empty( $defaults['noindex'] ) ) {
			$robots['noindex']  = true;
			$robots['nofollow'] = true;
			unset( $robots['index'], $robots['follow'] );
		}
		if ( is_singular() && get_post_meta( get_queried_object_id(), '_tusb_seo_noindex', true ) ) {
			$robots['noindex']  = true;
			$robots['nofollow'] = true;
			unset( $robots['index'], $robots['follow'] );
		}
		if ( is_search() || is_404() ) {
			$robots['noindex'] = true;
		}
		return $robots;
	}

	/**
	 * Add the sitemap to robots.txt when no SEO plugin does it.
	 *
	 * @param string $output Robots output.
	 * @param bool   $public Public site.
	 * @return string
	 */
	public function robots_txt( $output, $public ) {
		if ( ! $public ) {
			return $output;
		}
		if ( ! self::prints_meta() ) {
			return $output;
		}
		$sitemap = home_url( '/wp-sitemap.xml' );
		if ( false === strpos( $output, 'Sitemap:' ) ) {
			$output .= "\nSitemap: " . esc_url_raw( $sitemap ) . "\n";
		}
		return $output;
	}

	/**
	 * Report used by the SEO screen.
	 *
	 * @return array
	 */
	public function report() {
		$defaults   = self::defaults();
		$posts      = get_posts(
			array(
				'post_type'   => array( 'post', 'page' ),
				'post_status' => 'publish',
				'numberposts' => 200,
				'fields'      => 'ids',
			)
		);
		$missing_title = 0;
		$missing_desc  = 0;
		foreach ( $posts as $post_id ) {
			if ( ! get_post_meta( $post_id, '_tusb_seo_title', true ) ) {
				$missing_title++;
			}
			if ( ! get_post_meta( $post_id, '_tusb_seo_description', true ) ) {
				$missing_desc++;
			}
		}

		$images           = get_posts(
			array(
				'post_type'      => 'attachment',
				'post_mime_type' => 'image',
				'post_status'    => 'inherit',
				'numberposts'    => 500,
				'fields'         => 'ids',
			)
		);
		$missing_alt = 0;
		foreach ( $images as $image_id ) {
			if ( '' === trim( (string) get_post_meta( $image_id, '_wp_attachment_image_alt', true ) ) ) {
				$missing_alt++;
			}
		}

		return array(
			'prints_meta'    => self::prints_meta(),
			'other_plugins'  => TUSB_Compat::seo_plugins(),
			'posts'          => count( $posts ),
			'missing_title'  => $missing_title,
			'missing_desc'   => $missing_desc,
			'images'         => count( $images ),
			'missing_alt'    => $missing_alt,
			'sitemap'        => home_url( '/wp-sitemap.xml' ),
			'noindex'        => ! empty( $defaults['noindex'] ),
			'blog_public'    => (bool) get_option( 'blog_public' ),
			'defaults'       => $defaults,
			// Deliberately not offered: changing existing URLs. Permalinks belong
			// to the site owner and changing them breaks links and rankings.
			'urls_locked'    => (string) get_option( 'permalink_structure' ),
		);
	}
}
