def _get_profile_name(user):
    try:
        p = user.profile
        parts = [p.firstname, p.secondname, p.thirdname]
        name = ' '.join(x for x in parts if x)
        return name or user.mobile_number
    except Exception:
        return user.mobile_number
    
def _get_profile_image(user, request=None):
    try:
        if user.profile.image:
            url = user.profile.image.url
            return request.build_absolute_uri(url) if request else url
    except Exception:
        pass
    return None