from django.shortcuts import render
from django.views import View
from django.views.generic import TemplateView
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import requests
import ast
import pandas as pd
import pickle

Home = 'home.html'

qualified = pickle.load(open('qualified.pkl', 'rb'))
genre = pickle.load(open('gen_md.pkl', 'rb'))
genre_df = pickle.load(open('gen_df.pkl', 'rb'))
popular_df = pickle.load(open('Popular.pkl', 'rb'))
# popu_df = pickle.load(open('Popu_df.pkl', 'rb'))
movie_md = pickle.load(open('Popu_df.pkl', 'rb'))

# for recommendation
df = pickle.load(open('df.pkl', 'rb'))
similarity = pickle.load(open('similarity.pkl', 'rb'))
ratings = pickle.load(open('ratings.pkl', 'rb'))


def fetch_poster(movie_id):
    response = requests.get(
        f"https://api.themoviedb.org/3/movie/{movie_id}?api_key=60540559932077629483b29d4ef0559f&language=en-US")
    data = response.json()
    if 'poster_path' in data:
        return f"https://image.tmdb.org/t/p/w500/{data['poster_path']}"
    else:
        return None


@csrf_exempt
def jen(request):
    genre_list = genre_df[0].tolist()
    # converting each inner list to tuple
    # genre_tuples = [tuple(x) for x in genre_list]
    unique_genres = set(genre_list)

    if request.method == 'POST':
        movie_title = request.POST.get('movie_title')
        recommendations = recommend(movie_title)
        if recommendations is None:
            error_message = f"{movie_title} not found in the dataset. Please Enter another movie name!!"
            return render(request, Home, {'error_message': error_message})
        else:
            similar_movies = recommendations['similar_movies']
            recommended_movies = recommendations['recommended_movies']
            return render(request, Home, {'movie_title': movie_title, 'similar_movies': similar_movies, 'recommended_movies': recommended_movies})
    context = {'unique_genres': unique_genres}
    return render(request, Home, context)


def popular(request, num_movies=10):
    # Load the data from the pkl file into a pandas dataframe
    popular = pd.read_pickle("Popular.pkl")

    # Extract the columns from the dataframe
    movie_id = popular['id']
    titles = popular['original_title']

    # # Convert the string column to a list of dictionaries
    genres = popular['genres'].apply(ast.literal_eval)

    # Convert the genre column from a string to a list of dictionaries
    # genres = popular["genres"].apply(json.loads)

    # Extract the genre names from the list of dictionaries
    genre_names = [', '.join([genre['name'] for genre in movie])
                   for movie in genres]

    # Extracting the overview column
    overviews = popular['overview']

    # Use a list comprehension to create the list of movies
    movies = []
    for i in range(num_movies):
        poster_url = fetch_poster(movie_id[i])
        if poster_url:
            movie = {
                'movie_id': movie_id[i],
                'poster_url': poster_url,
                'title': titles[i],
                'genre': genres[i],
                'genre_names': genre_names[i],
                'overview': overviews[i]
            }
            movies.append(movie)

    context = {
        'movies': movies
    }

    # Render the template with the list of movies
    return render(request, 'popular.html', context)


def recommend(movie_title):
    # check if the movie is in the dataframe
    if movie_title not in df['title'].unique():
        return None

    # fetch index of the movie in the dataframe
    movie_index = df[df['title'] == movie_title].index[0]

    # use item-item similarity to get top similar movies
    distances = similarity[movie_index]
    movie_list = sorted(list(enumerate(distances)),
                        reverse=True, key=lambda x: x[1])[1:10]

    # top similar movies
    top_similar = []
    for i in movie_list:
        movie_data = {
            'id': df.iloc[i[0]].id,
            'title': df.iloc[i[0]].title,
            'overview': df.iloc[i[0]].tags,
            'poster': fetch_poster(df.iloc[i[0]].id) if not df[df['title'] == df.iloc[i[0]].title].empty else None
        }
        top_similar.append(movie_data)

    # use user-item collaborative filtering to get top rated movies by users
    user_ratings = ratings.merge(movie_md, on='id')
    user_ratings = user_ratings[['userId', 'original_title', 'rating']]

    if movie_title in user_ratings['original_title'].unique():
        pt = pd.pivot_table(user_ratings, values='rating',
                            index='userId', columns='original_title', fill_value=0)
        target_movie = pt[movie_title]
        similar_movies = pt.corrwith(target_movie)
        corr_target = pd.DataFrame(similar_movies, columns=['correlation'])
        corr_target.dropna(inplace=True)
        # corr_target = corr_target.join(movie_summary['weighted_average'])
        recommended_movies = corr_target[corr_target['correlation'] > 0.05].sort_values(
            by='correlation', ascending=False).head(5)

        # top recommended movies
        top_recommended = []
        for title in recommended_movies.index:
            poster_url = fetch_poster(
                df[df['title'] == title].iloc[0].id) if not df[df['title'] == title].empty else None
            top_recommended.append({
                'title': title,
                'poster': poster_url,
            })

        return {"similar_movies": top_similar, "recommended_movies": top_recommended}
    else:
        return {"similar_movies": top_similar, "recommended_movies": []}


@csrf_exempt
def recommend_movie(request):
    if request.method == 'POST':
        movie_title = request.POST.get('movie_title')
        results = recommend(movie_title)
        return JsonResponse(json.dumps(results), safe=False)
    else:
        return JsonResponse({"error": "Invalid request method"})
